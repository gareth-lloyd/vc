"""HoldService — Python-level lifecycle for `BookingHold` rows.

The DB-level `EXCLUDE` constraint (`bookinghold_no_overlap_live`) gates on
`status = LIVE` only — Postgres rejects `now()` in an index predicate — so an
expired-but-unswept hold still blocks at the DB level (BUG-005). Mutating
paths therefore opportunistically expire stale overlapping holds first
(`expire_overlapping_stale`), with the beat sweeper (`tasks.expire_holds`) as
the background pass, and translate any residual EXCLUDE violation (a true
concurrent race) into `HoldUnavailable` so the API contract holds.

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

from core.exceptions import HoldUnavailable, InvalidTransition
from core.locking import refresh_locked
from reservations.enums import BookingHoldReason, BookingHoldStatus
from reservations.models.booking import HOLD_OVERLAP_CONSTRAINT_NAME, BookingHold

if TYPE_CHECKING:
    from datetime import date as date_type

    from django.db.models import QuerySet

logger = structlog.get_logger(__name__)


def _resolve_default_expiry(property: Any) -> datetime:
    """Resolve the default hold expiry from the property's settings.

    Lazily ensures a `PropertySettings` row exists; a NULL
    `hold_duration_hours` falls back to 48 (the pre-GAP-070 group-floor
    default), so this never raises.
    """
    from properties.models import PropertySettings

    settings, _ = PropertySettings.objects.get_or_create(property=property)
    hours = settings.hold_duration_hours if settings.hold_duration_hours is not None else 48
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
        if HOLD_OVERLAP_CONSTRAINT_NAME not in str(exc):
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
        """Expire lapsed-but-unswept holds overlapping the range; return them.

        The opportunistic counterpart to `tasks.expire_holds` (BUG-005): the
        EXCLUDE constraint can't see `expires_at`, so if the beat sweeper is
        paused a lapsed hold would still block the INSERT at the DB level.
        Mutating paths call this first so a stale hold never blocks a valid
        booking. Shares `expire_lapsed` with the sweeper, so comms fan-out is
        identical whichever path expires the hold.
        """
        qs = BookingHold.objects.filter(
            property=property,
            date_from__lt=date_to,
            date_to__gt=date_from,
        )
        if exclude_hold_ids:
            qs = qs.exclude(pk__in=exclude_hold_ids)
        expired = cls.expire_lapsed(qs)
        if expired:
            logger.info(
                "hold.expired_opportunistic", released=len(expired), property_id=property.pk
            )
        return expired

    @classmethod
    def expire_lapsed(cls, holds: QuerySet[BookingHold] | None = None) -> list[BookingHold]:
        """Expire every LIVE hold in `holds` whose `expires_at` has passed.

        Per row, not a bulk update: each hold is re-checked under its lock
        (`_expire_one`), so one released, extended or moved since the SELECT is
        left alone and gets no `hold_expired`; and each expiry lands on the
        AuditLog trail. Rows are taken in pk order so two concurrent sweeps
        (inside `place`/`move`'s outer transaction) lock in the same order and
        can't deadlock. Fires `hold_expired` once per hold actually expired.
        NULL `expires_at` = indefinite block (owner/maintenance), never reaped.
        """
        from reservations.signals import hold_expired

        now = timezone.now()
        candidates = list(
            (holds if holds is not None else BookingHold.objects.all())
            .filter(
                status=BookingHoldStatus.LIVE.value,
                expires_at__isnull=False,
                expires_at__lt=now,
            )
            .order_by("pk")
        )
        expired = []
        for hold in candidates:
            if cls._expire_one(hold, now):
                # Per row, not after the loop: in the beat sweep each expiry
                # commits alone, so a later row failing must not strand the
                # emails of rows already EXPIRED (never re-selected).
                hold_expired.send(sender=BookingHold, hold=hold)
                expired.append(hold)
        return expired

    @classmethod
    def _expire_one(cls, hold: BookingHold, now: datetime) -> bool:
        """Expire `hold` iff it still exists, is LIVE and lapsed on the locked row."""
        with transaction.atomic():
            try:
                refresh_locked(hold)
            except BookingHold.DoesNotExist:
                # Deleted since the SELECT (cascade from its quotation/booking).
                return False
            lapsed = hold.expires_at is not None and hold.expires_at < now
            if hold.status != BookingHoldStatus.LIVE.value or not lapsed:
                return False
            hold.expire(now=now)
        return True

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
                status=BookingHoldStatus.LIVE.value,
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
        `now() + property.settings.hold_duration_hours` (48 when unset). Callers
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
    def release(cls, hold: BookingHold) -> BookingHold:
        """Release a single hold right now; a no-op on an already-closed hold.

        Idempotent so a double-click (or a release racing the sweeper) stays a
        200: an EXPIRED hold keeps its status rather than being relabelled.
        """
        if hold.status != BookingHoldStatus.LIVE.value:
            return hold
        try:
            hold.release()
        except InvalidTransition:
            # LIVE is the only from-state, so a refusal on the locked row means
            # someone else closed it first; `hold` now carries that status.
            return hold
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
            status=BookingHoldStatus.LIVE.value,
        ).update(status=BookingHoldStatus.RELEASED.value, released_at=timezone.now())

    @classmethod
    @transaction.atomic
    def release_for_quotation(cls, quotation: Any) -> int:
        """Release every live hold tied to a given quotation. Returns count."""
        now = timezone.now()
        return BookingHold.objects.filter(
            quotation=quotation,
            status=BookingHoldStatus.LIVE.value,
        ).update(status=BookingHoldStatus.RELEASED.value, released_at=now)

    @classmethod
    @transaction.atomic
    def release_for_booking(cls, booking: Any) -> int:
        """Release every live hold tied to a given booking. Returns count."""
        now = timezone.now()
        return BookingHold.objects.filter(
            booking=booking,
            status=BookingHoldStatus.LIVE.value,
        ).update(status=BookingHoldStatus.RELEASED.value, released_at=now)
