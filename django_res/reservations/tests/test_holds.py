"""Tests for `HoldService` — Python-level overlap check + release."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from core.exceptions import HoldUnavailable
from reservations.enums import BookingHoldReason
from reservations.models import BookingHold
from reservations.services.holds import HoldService
from reservations.tasks import expire_holds

if TYPE_CHECKING:
    from properties.models import Property


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
    assert hold.released_at == first_release


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
    assert HoldService.expire_due() == []
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
