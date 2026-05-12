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
