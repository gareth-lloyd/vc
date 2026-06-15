"""HoldService — Python-level lifecycle for `BookingHold` rows.

The DB-level `EXCLUDE` constraint (`bookinghold_no_overlap_live`,
migration 0002) gates on `released_at IS NULL` only — Postgres rejects
`now()` in an index predicate — so an expired-but-unswept hold still
blocks at the DB level (BUG-005). Mutating paths therefore
opportunistically release stale overlapping holds first
(`expire_overlapping_stale`), with the beat sweeper
(`tasks.expire_holds`) as the background pass, and translate any
residual EXCLUDE violation (a true concurrent race) into
`HoldUnavailable` so the API contract holds.

All mutations run inside `transaction.atomic` so the place/release
operations remain consistent even if a later step in the calling service
fails.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import HoldUnavailable
from reservations.enums import BookingHoldReason
from reservations.models.booking import BookingHold

if TYPE_CHECKING:
    from datetime import date as date_type

logger = structlog.get_logger(__name__)


def _resolve_default_expiry(property: Any) -> datetime:
    """Resolve the default hold expiry from the property's effective settings.

    Lazily ensures a `PropertySettings` row exists so the inheritance chain
    resolves cleanly to the group default when no per-property override is
    set. The group fallback (48 hours by default) means this never raises.
    """
    from properties.models import PropertySettings

    settings, _ = PropertySettings.objects.get_or_create(property=property)
    hours = settings.effective("hold_duration_hours")
    return timezone.now() + timedelta(hours=hours)


@contextmanager
def _translate_overlap_violation(property: Any, date_from: date_type, date_to: date_type) -> Any:
    """Re-raise a `bookinghold_no_overlap_live` violation as `HoldUnavailable`.

    The EXCLUDE constraint is the concurrency backstop: when a competing hold
    commits between `_assert_no_overlap` and the INSERT/UPDATE, the violation
    must surface as the documented 409, not a raw 500. Any other
    `IntegrityError` propagates untouched. No queries run between catching and
    re-raising, so the aborted transaction state is never touched.
    """
    try:
        yield
    except IntegrityError as exc:
        if "bookinghold_no_overlap_live" not in str(exc):
            raise
        raise HoldUnavailable(
            f"{property} is unavailable for {date_from}..{date_to} — "
            "another hold was placed on these dates concurrently."
        ) from exc


class HoldService:
    """Place / release / expire `BookingHold` rows."""

    @classmethod
    def expire_overlapping_stale(
        cls,
        *,
        property: Any,
        date_from: date_type,
        date_to: date_type,
        exclude_hold_ids: list[int] | None = None,
    ) -> list[BookingHold]:
        """Release expired-but-unswept holds overlapping the range; return them.

        The opportunistic counterpart to `tasks.expire_holds` (BUG-005): the
        EXCLUDE constraint can't see `expires_at`, so if the beat sweeper is
        paused an expired hold would still block the INSERT at the DB level.
        Mutating paths call this first so a stale hold never blocks a valid
        booking. Fires `hold_expired` per row, exactly like the sweeper, so
        comms fan-out is identical whichever path releases the hold.
        """
        from reservations.signals import hold_expired

        now = timezone.now()
        qs = BookingHold.objects.filter(
            property=property,
            released_at__isnull=True,
            expires_at__isnull=False,
            expires_at__lt=now,
            date_from__lt=date_to,
            date_to__gt=date_from,
        )
        if exclude_hold_ids:
            qs = qs.exclude(pk__in=exclude_hold_ids)
        due = list(qs)
        if not due:
            return []
        BookingHold.objects.filter(pk__in=[hold.pk for hold in due]).update(released_at=now)
        for hold in due:
            # Refresh the in-memory copy so signal handlers see post-update state.
            hold.released_at = now
            hold_expired.send(sender=BookingHold, hold=hold)
        logger.info("hold.expired_opportunistic", released=len(due), property_id=property.pk)
        return due

    @classmethod
    def _assert_no_overlap(
        cls,
        *,
        property: Any,
        date_from: date_type,
        date_to: date_type,
        exclude_hold_ids: list[int] | None = None,
    ) -> None:
        """Raise `HoldUnavailable` if a live hold overlaps the range.

        The shared conflict guard for `place` (new hold) and `move`/
        `update_block` (relocate, excluding the hold itself) — one predicate so
        the overlap rule can't drift between create and edit. The error message
        is operator-facing (the SPA toasts it verbatim), so it names the villa
        and whoever owns the blocking hold rather than bare pks.
        """
        hold = (
            BookingHold.live_overlapping(
                property=property,
                date_from=date_from,
                date_to=date_to,
                exclude_ids=exclude_hold_ids,
            )
            .select_related("quotation", "booking")
            .first()
        )
        if hold is None:
            return
        if hold.quotation_id:
            owner = f"quotation {hold.quotation.reference}"
        elif hold.booking_id:
            owner = f"booking {hold.booking.reference}"
        else:
            owner = f"a {hold.get_reason_display().lower()} hold"
        expiry = (
            # localtime: the operator reads this in `TIME_ZONE`, not UTC.
            f" until {timezone.localtime(hold.expires_at):%d %b %Y %H:%M %Z}"
            if hold.expires_at
            else ""
        )
        raise HoldUnavailable(
            f"{property} is unavailable for {date_from}..{date_to} — "
            f"{hold.date_from}..{hold.date_to} is already held by {owner}{expiry}."
        )

    @classmethod
    def assert_no_foreign_hold(
        cls,
        *,
        property: Any,
        date_from: date_type,
        date_to: date_type,
        quotation: Any,
    ) -> None:
        """Raise `HoldUnavailable` if a live hold NOT owned by `quotation` overlaps.

        The convert-time guard: with quoting no longer auto-holding its dates,
        another party may have held the villa between quote and accept. The
        quotation's own line holds are excluded so they never block their own
        conversion.
        """
        own_hold_ids = list(
            BookingHold.objects.filter(
                quotation=quotation,
                released_at__isnull=True,
            ).values_list("pk", flat=True)
        )
        cls._assert_no_overlap(
            property=property,
            date_from=date_from,
            date_to=date_to,
            exclude_hold_ids=own_hold_ids or None,
        )

    @classmethod
    @transaction.atomic
    def place(
        cls,
        *,
        property: Any,
        date_from: date_type,
        date_to: date_type,
        expires_at: datetime | None = None,
        never_expires: bool = False,
        reason: str = BookingHoldReason.MANUAL.value,
        quotation: Any = None,
        quotation_line: Any = None,
        booking: Any = None,
        notes: str = "",
    ) -> BookingHold:
        """Place a live hold; raises `HoldUnavailable` if one already overlaps.

        When `expires_at` is omitted, defaults to
        `now() + property.settings.effective("hold_duration_hours")`. Callers
        may always pass an explicit value to override the per-villa default.

        Pass `never_expires=True` for indefinite blocks (owner / maintenance):
        the hold is stored with `expires_at=None` and `tasks.expire_holds`
        never reaps it. `never_expires` and an explicit `expires_at` are
        mutually exclusive.
        """
        cls.expire_overlapping_stale(property=property, date_from=date_from, date_to=date_to)
        cls._assert_no_overlap(property=property, date_from=date_from, date_to=date_to)
        if never_expires:
            if expires_at is not None:
                raise ValueError("`never_expires=True` cannot be combined with `expires_at`")
        elif expires_at is None:
            expires_at = _resolve_default_expiry(property)
        with _translate_overlap_violation(property, date_from, date_to):
            return BookingHold.objects.create(
                property=property,
                quotation=quotation,
                quotation_line=quotation_line,
                booking=booking,
                date_from=date_from,
                date_to=date_to,
                expires_at=expires_at,
                reason=reason,
                notes=notes,
            )

    @classmethod
    @transaction.atomic
    def update_block(
        cls,
        hold: BookingHold,
        *,
        date_from: date_type,
        date_to: date_type,
        reason: str,
        notes: str,
    ) -> BookingHold:
        """Edit an operator block in place; re-checks overlap excluding itself.

        Raises `HoldUnavailable` if the new range collides with another live
        hold (the editing hold is excluded so a no-op save is allowed).
        """
        cls.expire_overlapping_stale(
            property=hold.property,
            date_from=date_from,
            date_to=date_to,
            exclude_hold_ids=[hold.pk],
        )
        cls._assert_no_overlap(
            property=hold.property,
            date_from=date_from,
            date_to=date_to,
            exclude_hold_ids=[hold.pk],
        )
        hold.date_from = date_from
        hold.date_to = date_to
        hold.reason = reason
        hold.notes = notes
        with _translate_overlap_violation(hold.property, date_from, date_to):
            hold.save(update_fields=["date_from", "date_to", "reason", "notes", "updated_at"])
        return hold

    @classmethod
    @transaction.atomic
    def move(
        cls,
        hold: BookingHold,
        *,
        date_from: date_type,
        date_to: date_type,
        expires_at: datetime | None = None,
    ) -> BookingHold:
        """Relocate a live hold's date range (and optionally its expiry) in place.

        Re-checks overlap excluding the hold itself, so a date change that
        collides with *another* live hold raises `HoldUnavailable`. Used to keep
        a quotation line's hold aligned when the line is repriced or edited
        (e.g. a changeover-shifted arrival). Distinct from `update_block`, which
        is the operator-block editor and rewrites reason/notes instead.
        """
        cls.expire_overlapping_stale(
            property=hold.property,
            date_from=date_from,
            date_to=date_to,
            exclude_hold_ids=[hold.pk],
        )
        cls._assert_no_overlap(
            property=hold.property,
            date_from=date_from,
            date_to=date_to,
            exclude_hold_ids=[hold.pk],
        )
        hold.date_from = date_from
        hold.date_to = date_to
        update_fields = ["date_from", "date_to", "updated_at"]
        if expires_at is not None:
            hold.expires_at = expires_at
            update_fields.append("expires_at")
        with _translate_overlap_violation(hold.property, date_from, date_to):
            hold.save(update_fields=update_fields)
        return hold

    @classmethod
    @transaction.atomic
    def release(cls, hold: BookingHold) -> BookingHold:
        """Mark a single hold as released right now."""
        if hold.released_at is not None:
            return hold
        hold.released_at = timezone.now()
        hold.save(update_fields=["released_at", "updated_at"])
        return hold

    @classmethod
    @transaction.atomic
    def release_for_line(cls, line: Any) -> int:
        """Release every live hold tied to a given quotation line. Returns count.

        Fired from the `QuotationLine` pre_delete signal so a deleted line frees
        its dates whatever the delete path (API, ORM, cascade) — and used as the
        bulk counterpart to `release_for_quotation` / `release_for_booking`.
        """
        return BookingHold.objects.filter(
            quotation_line=line,
            released_at__isnull=True,
        ).update(released_at=timezone.now())

    @classmethod
    @transaction.atomic
    def release_for_quotation(cls, quotation: Any) -> int:
        """Release every live hold tied to a given quotation. Returns count."""
        now = timezone.now()
        return BookingHold.objects.filter(
            quotation=quotation,
            released_at__isnull=True,
        ).update(released_at=now)

    @classmethod
    @transaction.atomic
    def release_for_booking(cls, booking: Any) -> int:
        """Release every live hold tied to a given booking. Returns count."""
        now = timezone.now()
        return BookingHold.objects.filter(
            booking=booking,
            released_at__isnull=True,
        ).update(released_at=now)

    @classmethod
    def expire_due(cls) -> list[int]:
        """Mark holds past their `expires_at` as released; return ids touched.

        The actual signal fan-out happens in `reservations.tasks.expire_holds`.
        This helper is the underlying DB operation.
        """
        now = timezone.now()
        # `expires_at__lt` already excludes NULL rows in SQL, but the explicit
        # `isnull=False` documents that indefinite holds are never reaped.
        due_ids = list(
            BookingHold.objects.filter(
                released_at__isnull=True,
                expires_at__isnull=False,
                expires_at__lt=now,
            ).values_list("pk", flat=True)
        )
        if not due_ids:
            return []
        BookingHold.objects.filter(pk__in=due_ids).update(released_at=now)
        return due_ids
