"""Tests for `HoldService` — Python-level overlap check + release."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from core.exceptions import DomainValidationError, HoldUnavailable, ReadOnlyHold
from reservations.enums import BookingHoldReason, BookingHoldStatus
from reservations.models import BookingHold
from reservations.services.holds import HoldService
from reservations.tasks import expire_holds

if TYPE_CHECKING:
    from properties.models import Property
    from reservations.models import QuotationLine


@pytest.mark.django_db
def test_place_creates_live_hold(property_: Property) -> None:
    expires = timezone.now() + timedelta(hours=1)
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=expires,
        reason=BookingHoldReason.MANUAL.value,
    )
    assert hold.released_at is None
    assert hold.is_live() is True


@pytest.mark.django_db
def test_place_refuses_overlapping_live_hold(property_: Property) -> None:
    expires = timezone.now() + timedelta(hours=1)
    HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=expires,
    )
    with pytest.raises(HoldUnavailable):
        HoldService.place(
            property=property_,
            date_from=date(2026, 6, 12),
            date_to=date(2026, 6, 20),
            expires_at=expires,
        )


@pytest.mark.django_db
def test_overlap_error_names_property_and_owning_quotation(
    property_: Property, quotation_line: QuotationLine
) -> None:
    """The conflict message is operator-readable: villa name + blocking quote ref."""
    HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(hours=1),
        reason=BookingHoldReason.QUOTATION_OPEN.value,
        quotation=quotation_line.quotation,
        quotation_line=quotation_line,
    )
    with pytest.raises(HoldUnavailable) as excinfo:
        HoldService.place(
            property=property_,
            date_from=date(2026, 6, 12),
            date_to=date(2026, 6, 20),
            expires_at=timezone.now() + timedelta(hours=1),
        )
    message = str(excinfo.value)
    assert str(property_) in message
    assert quotation_line.quotation.reference in message
    assert "2026-06-12" in message and "2026-06-20" in message


@pytest.mark.django_db
def test_overlap_error_names_block_reason_without_quotation(property_: Property) -> None:
    """A plain operator block reports its reason rather than a bare property pk."""
    HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        reason=BookingHoldReason.OWNER_BLOCK.value,
        never_expires=True,
    )
    with pytest.raises(HoldUnavailable) as excinfo:
        HoldService.place(
            property=property_,
            date_from=date(2026, 6, 12),
            date_to=date(2026, 6, 20),
            expires_at=timezone.now() + timedelta(hours=1),
        )
    message = str(excinfo.value)
    assert str(property_) in message
    assert "owner block" in message.lower()


@pytest.mark.django_db
def test_overlap_error_shows_expiry_in_local_time(property_: Property) -> None:
    """The expiry in the conflict message is operator-local (`TIME_ZONE`), not UTC."""
    from datetime import UTC, datetime

    from django.test import override_settings

    HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        # 09:00 UTC == 11:00 EET in Athens (winter).
        expires_at=datetime(2030, 1, 10, 9, 0, tzinfo=UTC),
    )
    with override_settings(TIME_ZONE="Europe/Athens"), pytest.raises(HoldUnavailable) as excinfo:
        HoldService.place(
            property=property_,
            date_from=date(2026, 6, 12),
            date_to=date(2026, 6, 20),
            expires_at=timezone.now() + timedelta(hours=1),
        )
    assert "10 Jan 2030 11:00 EET" in str(excinfo.value)


@pytest.mark.django_db
def test_place_allows_overlap_when_prior_hold_released(property_: Property) -> None:
    expires = timezone.now() + timedelta(hours=1)
    first = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=expires,
    )
    HoldService.release(first)
    # Same range — should be allowed.
    second = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=expires,
    )
    assert second.pk != first.pk


@pytest.mark.django_db
def test_release_for_line_bulk_releases_live_holds(
    property_: Property, quotation_line: QuotationLine
) -> None:
    """`release_for_line` releases every live hold tied to a line in one pass."""
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(hours=1),
        reason=BookingHoldReason.QUOTATION_OPEN.value,
        quotation=quotation_line.quotation,
        quotation_line=quotation_line,
    )
    released = HoldService.release_for_line(quotation_line)
    assert released == 1
    hold.refresh_from_db()
    assert hold.status == BookingHoldStatus.RELEASED.value
    assert hold.released_at is not None
    assert hold.is_live() is False


@pytest.mark.django_db
def test_deleting_line_releases_its_holds_via_signal(
    property_: Property, quotation_line: QuotationLine
) -> None:
    """Deleting a QuotationLine through the ORM (no viewset) still releases its
    live holds — the invariant lives at the model layer, not just the API."""
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(hours=1),
        reason=BookingHoldReason.QUOTATION_OPEN.value,
        quotation=quotation_line.quotation,
        quotation_line=quotation_line,
    )
    quotation_line.delete()

    hold.refresh_from_db()
    assert hold.status == BookingHoldStatus.RELEASED.value
    assert hold.released_at is not None
    assert hold.is_live() is False


@pytest.mark.django_db
def test_release_idempotent(property_: Property) -> None:
    expires = timezone.now() + timedelta(hours=1)
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=expires,
    )
    HoldService.release(hold)
    first_release = hold.released_at
    HoldService.release(hold)
    hold.refresh_from_db()
    assert hold.status == BookingHoldStatus.RELEASED.value
    assert hold.released_at == first_release


@pytest.mark.django_db
def test_release_is_a_no_op_on_expired_hold(property_: Property) -> None:
    """Releasing a hold the sweeper already expired keeps it EXPIRED — the
    record of which close happened (and so whether the agent was emailed)."""
    hold = _stale_hold(property_)
    expire_holds()
    hold.refresh_from_db()
    expired_at = hold.released_at

    HoldService.release(hold)

    hold.refresh_from_db()
    assert hold.status == BookingHoldStatus.EXPIRED.value
    assert hold.released_at == expired_at


@pytest.mark.django_db
def test_release_on_stale_instance_is_a_no_op(property_: Property) -> None:
    """A stale in-memory LIVE copy of an already-expired hold (double-click,
    sweeper race) is refused under the lock and returned, not a 409."""
    hold = _stale_hold(property_)
    stale = BookingHold.objects.get(pk=hold.pk)
    expire_holds()

    returned = HoldService.release(stale)

    assert returned.status == BookingHoldStatus.EXPIRED.value
    hold.refresh_from_db()
    assert hold.status == BookingHoldStatus.EXPIRED.value


@pytest.mark.django_db
def test_release_for_quotation_and_booking_set_released(
    property_: Property, quotation_line: QuotationLine
) -> None:
    quotation = quotation_line.quotation
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(hours=1),
        reason=BookingHoldReason.QUOTATION_OPEN.value,
        quotation=quotation,
    )
    closed = _stale_hold(property_, date_from=date(2026, 8, 1), date_to=date(2026, 8, 8))
    expire_holds()
    BookingHold.objects.filter(pk=closed.pk).update(quotation=quotation)

    assert HoldService.release_for_quotation(quotation) == 1

    hold.refresh_from_db()
    closed.refresh_from_db()
    assert hold.status == BookingHoldStatus.RELEASED.value
    assert closed.status == BookingHoldStatus.EXPIRED.value


@pytest.mark.django_db
def test_hold_creation_uses_effective_setting(property_: Property) -> None:
    """When `expires_at` is omitted, `place` defaults to now + effective hours."""
    from properties.models import PropertySettings

    PropertySettings.objects.create(property=property_, hold_duration_hours=24)
    before = timezone.now()
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    after = timezone.now()

    # Tolerate test execution time on either side of the now() call.
    assert hold.expires_at is not None
    assert before + timedelta(hours=24) <= hold.expires_at <= after + timedelta(hours=24)


@pytest.mark.django_db
def test_hold_creation_falls_back_to_group_default(property_: Property) -> None:
    """No PropertySettings row at all → use the group default (48 hours)."""
    before = timezone.now()
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    after = timezone.now()

    assert hold.expires_at is not None
    assert before + timedelta(hours=48) <= hold.expires_at <= after + timedelta(hours=48)


@pytest.mark.django_db
def test_hold_caller_expires_at_override_wins(property_: Property) -> None:
    """An explicit `expires_at` beats the resolved effective setting."""
    from properties.models import PropertySettings

    PropertySettings.objects.create(property=property_, hold_duration_hours=24)
    explicit = timezone.now() + timedelta(hours=1)
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=explicit,
    )

    assert hold.expires_at == explicit


@pytest.mark.django_db
def test_expire_holds_task_releases_past_due(property_: Property) -> None:
    past = timezone.now() - timedelta(minutes=5)
    BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=past,
        reason=BookingHoldReason.MANUAL.value,
    )
    ids = expire_holds()
    assert len(ids) == 1
    hold = BookingHold.objects.get(pk=ids[0])
    assert hold.status == BookingHoldStatus.EXPIRED.value
    assert hold.released_at is not None


@pytest.mark.django_db
def test_place_never_expires_stores_null_expiry(property_: Property) -> None:
    """An owner/maintenance block is placed with no expiry and reads as live."""
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        reason=BookingHoldReason.OWNER_BLOCK.value,
        never_expires=True,
    )
    assert hold.expires_at is None
    assert hold.is_live() is True


@pytest.mark.django_db
def test_indefinite_hold_survives_expire_holds(property_: Property) -> None:
    """A null-expiry hold is never reaped by the expiry task and stays overlapping."""
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        reason=BookingHoldReason.OWNER_BLOCK.value,
        never_expires=True,
    )
    assert expire_holds() == []
    hold.refresh_from_db()
    assert hold.released_at is None
    assert hold.is_live() is True
    assert (
        BookingHold.live_overlapping(
            property=property_,
            date_from=date(2026, 6, 12),
            date_to=date(2026, 6, 14),
        )
        .filter(pk=hold.pk)
        .exists()
    )


# ---------------------------------------------------------------------------
# BUG-005 — stale (expired-but-unswept) holds must not block valid mutations,
# and the Postgres EXCLUDE backstop must surface as `HoldUnavailable`, not 500.
# ---------------------------------------------------------------------------


def _stale_hold(
    property_: Property,
    *,
    date_from: date = date(2026, 6, 10),
    date_to: date = date(2026, 6, 17),
) -> BookingHold:
    """An expired hold the sweeper hasn't released yet (sweeper paused)."""
    return BookingHold.objects.create(
        property=property_,
        date_from=date_from,
        date_to=date_to,
        expires_at=timezone.now() - timedelta(minutes=5),
    )


@pytest.mark.django_db
def test_expire_holds_skips_hold_released_after_selection(
    property_: Property, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-H2: a hold released between the sweep's SELECT and its per-row lock is
    left RELEASED and fires no `hold_expired` (no wrong agent email)."""
    from reservations.signals import hold_expired

    hold = _stale_hold(property_)
    original = HoldService._expire_one

    def release_first(selected: BookingHold, now: datetime) -> bool:
        HoldService.release(BookingHold.objects.get(pk=selected.pk))
        return original(selected, now)

    monkeypatch.setattr(HoldService, "_expire_one", release_first)
    seen: list[BookingHold] = []

    def receiver(sender: object, hold: BookingHold, **kwargs: object) -> None:
        seen.append(hold)

    hold_expired.connect(receiver)
    try:
        assert expire_holds() == []
    finally:
        hold_expired.disconnect(receiver)
    assert seen == []
    hold.refresh_from_db()
    assert hold.status == BookingHoldStatus.RELEASED.value


@pytest.mark.django_db
def test_expire_skips_hold_deleted_after_selection(property_: Property) -> None:
    """A hold deleted (e.g. with its draft quotation) between the sweep's SELECT
    and its per-row lock is skipped, not a crash that aborts the sweep."""
    hold = _stale_hold(property_)
    selected = BookingHold.objects.get(pk=hold.pk)
    hold.delete()

    assert HoldService._expire_one(selected, timezone.now()) is False


@pytest.mark.django_db
def test_expire_skips_hold_extended_after_selection(property_: Property) -> None:
    """R-H2: a stale selected copy of a hold whose expiry was pushed out since
    is not expired — the lapse is re-checked on the locked row."""
    hold = _stale_hold(property_)
    selected = BookingHold.objects.get(pk=hold.pk)
    extended = timezone.now() + timedelta(hours=1)
    BookingHold.objects.filter(pk=hold.pk).update(expires_at=extended)

    assert HoldService._expire_one(selected, timezone.now()) is False

    hold.refresh_from_db()
    assert hold.status == BookingHoldStatus.LIVE.value
    assert hold.released_at is None
    assert hold.expires_at == extended


@pytest.mark.django_db
def test_place_succeeds_over_expired_unswept_hold(property_: Property) -> None:
    """Acceptance: an expired-but-unreleased hold must not block a new one."""
    stale = _stale_hold(property_)
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    assert hold.is_live() is True
    stale.refresh_from_db()
    assert stale.status == BookingHoldStatus.EXPIRED.value
    assert stale.released_at is not None


@pytest.mark.django_db
def test_place_opportunistic_expiry_fires_hold_expired_signal(property_: Property) -> None:
    """Opportunistic expiry fans out `hold_expired` exactly like the sweeper."""
    from reservations.signals import hold_expired

    stale = _stale_hold(property_)
    seen: list[BookingHold] = []

    def receiver(sender: object, hold: BookingHold, **kwargs: object) -> None:
        seen.append(hold)

    hold_expired.connect(receiver)
    try:
        HoldService.place(
            property=property_,
            date_from=date(2026, 6, 10),
            date_to=date(2026, 6, 17),
            expires_at=timezone.now() + timedelta(hours=1),
        )
    finally:
        hold_expired.disconnect(receiver)
    assert [h.pk for h in seen] == [stale.pk]
    assert seen[0].released_at is not None


@pytest.mark.django_db
def test_move_succeeds_over_expired_unswept_hold(property_: Property) -> None:
    stale = _stale_hold(property_)
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    moved = HoldService.move(hold, date_from=date(2026, 6, 10), date_to=date(2026, 6, 17))
    assert moved.date_from == date(2026, 6, 10)
    stale.refresh_from_db()
    assert stale.released_at is not None


@pytest.mark.django_db
def test_update_block_succeeds_over_expired_unswept_hold(property_: Property) -> None:
    stale = _stale_hold(property_)
    block = HoldService.place(
        property=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        reason=BookingHoldReason.MAINTENANCE.value,
        never_expires=True,
    )
    updated = HoldService.update_block(
        block,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        reason=BookingHoldReason.MAINTENANCE.value,
        notes="repainting",
    )
    assert updated.date_from == date(2026, 6, 10)
    stale.refresh_from_db()
    assert stale.released_at is not None


@pytest.mark.django_db
def test_place_race_raises_hold_unavailable_not_integrity_error(
    property_: Property, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a competing hold lands between the Python check and the INSERT, the
    Postgres EXCLUDE violation must surface as `HoldUnavailable` (409), not a
    raw `IntegrityError` (500)."""
    from django.db import connection

    if connection.vendor != "postgresql":
        pytest.skip("EXCLUDE constraint is Postgres-only")
    HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    # Simulate the race: the Python liveness check sees no conflict.
    monkeypatch.setattr(HoldService, "_assert_no_overlap", classmethod(lambda cls, **kw: None))
    with pytest.raises(HoldUnavailable):
        HoldService.place(
            property=property_,
            date_from=date(2026, 6, 12),
            date_to=date(2026, 6, 20),
            expires_at=timezone.now() + timedelta(hours=1),
        )


# ---------------------------------------------------------------------------
# BUG-015 U8b — edits refuse closed holds; explicit expiries must be future.
# ---------------------------------------------------------------------------


def _closed_hold(property_: Property, status: str) -> BookingHold:
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    stale = BookingHold.objects.get(pk=hold.pk)
    if status == BookingHoldStatus.RELEASED.value:
        hold.release()
    else:
        hold.expire()
    # A stale LIVE copy: the guard must read the locked row, not this.
    return stale


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status", [BookingHoldStatus.RELEASED.value, BookingHoldStatus.EXPIRED.value]
)
def test_update_block_refuses_closed_hold(property_: Property, status: str) -> None:
    stale = _closed_hold(property_, status)

    with pytest.raises(ReadOnlyHold):
        HoldService.update_block(
            stale,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 8),
            reason=BookingHoldReason.MAINTENANCE.value,
            notes="x",
        )

    fresh = BookingHold.objects.get(pk=stale.pk)
    assert fresh.date_from == date(2026, 6, 10)
    assert fresh.status == status


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status", [BookingHoldStatus.RELEASED.value, BookingHoldStatus.EXPIRED.value]
)
def test_move_refuses_closed_hold(property_: Property, status: str) -> None:
    stale = _closed_hold(property_, status)

    with pytest.raises(ReadOnlyHold):
        HoldService.move(stale, date_from=date(2026, 7, 1), date_to=date(2026, 7, 8))

    assert BookingHold.objects.get(pk=stale.pk).date_from == date(2026, 6, 10)


@pytest.mark.django_db
def test_update_block_and_move_refuse_lapsed_unswept_hold(property_: Property) -> None:
    """Editing a lapsed hold would revive it behind the sweeper's back (every
    live reader already treats it as gone) — same rule as `extend`."""
    stale = _stale_hold(property_)

    with pytest.raises(ReadOnlyHold):
        HoldService.update_block(
            stale,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 8),
            reason=BookingHoldReason.MAINTENANCE.value,
            notes="x",
        )
    with pytest.raises(ReadOnlyHold):
        HoldService.move(
            stale,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 8),
            expires_at=timezone.now() + timedelta(days=3),
        )

    fresh = BookingHold.objects.get(pk=stale.pk)
    assert fresh.date_from == date(2026, 6, 10)
    assert fresh.status == BookingHoldStatus.LIVE.value


@pytest.mark.django_db
def test_place_rejects_past_expiry(property_: Property) -> None:
    with pytest.raises(DomainValidationError) as exc:
        HoldService.place(
            property=property_,
            date_from=date(2026, 6, 10),
            date_to=date(2026, 6, 17),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
    assert "expires_at" in exc.value.field_errors
    assert not BookingHold.objects.exists()


@pytest.mark.django_db
def test_place_default_expiry_is_not_future_checked(property_: Property) -> None:
    """The resolved default is the property's own setting, not operator input:
    a 0-hour duration is a (flagged) config problem, not a 400."""
    from properties.models import PropertySettings

    PropertySettings.objects.create(property=property_, hold_duration_hours=0)

    hold = HoldService.place(
        property=property_, date_from=date(2026, 6, 10), date_to=date(2026, 6, 17)
    )

    assert hold.pk is not None


@pytest.mark.django_db
def test_move_rejects_past_expiry(property_: Property) -> None:
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(hours=1),
    )

    with pytest.raises(DomainValidationError):
        HoldService.move(
            hold,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 8),
            expires_at=timezone.now() - timedelta(minutes=1),
        )

    assert BookingHold.objects.get(pk=hold.pk).date_from == date(2026, 6, 10)


@pytest.mark.django_db
def test_extend_pushes_expiry_out(property_: Property) -> None:
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    new_expiry = timezone.now() + timedelta(days=3)

    returned = HoldService.extend(hold, expires_at=new_expiry)

    assert returned.expires_at == new_expiry
    hold.refresh_from_db()
    assert hold.expires_at == new_expiry
    assert hold.status == BookingHoldStatus.LIVE.value


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status", [BookingHoldStatus.RELEASED.value, BookingHoldStatus.EXPIRED.value]
)
def test_extend_refuses_closed_hold(property_: Property, status: str) -> None:
    stale = _closed_hold(property_, status)

    with pytest.raises(ReadOnlyHold):
        HoldService.extend(stale, expires_at=timezone.now() + timedelta(days=3))


@pytest.mark.django_db
def test_extend_refuses_lapsed_unswept_hold(property_: Property) -> None:
    """Reviving a lapsed hold would un-expire it behind the sweeper's back
    (its dates may already be re-held); place a new hold instead."""
    stale = _stale_hold(property_)
    expired_at = stale.expires_at

    with pytest.raises(ReadOnlyHold):
        HoldService.extend(stale, expires_at=timezone.now() + timedelta(days=3))

    assert BookingHold.objects.get(pk=stale.pk).expires_at == expired_at


@pytest.mark.django_db
def test_extend_refuses_indefinite_block(property_: Property) -> None:
    block = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        reason=BookingHoldReason.OWNER_BLOCK.value,
        never_expires=True,
    )

    with pytest.raises(ReadOnlyHold):
        HoldService.extend(block, expires_at=timezone.now() + timedelta(days=3))

    assert BookingHold.objects.get(pk=block.pk).expires_at is None


@pytest.mark.django_db
def test_extend_rejects_past_expiry(property_: Property) -> None:
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(hours=1),
    )

    with pytest.raises(DomainValidationError):
        HoldService.extend(hold, expires_at=timezone.now() - timedelta(minutes=1))
