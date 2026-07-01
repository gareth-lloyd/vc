"""PropertyAvailabilityService — the two freshness-touch primitives (GAP-033).

Signal 1 ("last updated by owner") and Signal 3 ("last confirmed by VC staff")
are plain timestamp columns on `Property`, written only through this service.
A freshness touch is deliberately *not* a property edit, so it must never bump
`updated_at` (which drives "recently updated" sorts).
"""

from __future__ import annotations

import pytest

from accounts.models import User
from core.enums import StaffRole
from properties.models import Property
from properties.services import PropertyAvailabilityService

pytestmark = pytest.mark.django_db


@pytest.fixture
def actor() -> User:
    return User.objects.create_user(
        is_staff=True,
        email="confirmer@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


def test_confirm_sets_timestamp_and_actor(property_: Property, actor: User) -> None:
    assert property_.availability_confirmed_at is None
    assert property_.availability_confirmed_by_id is None

    PropertyAvailabilityService.confirm(property_, actor=actor)

    property_.refresh_from_db()
    assert property_.availability_confirmed_at is not None
    assert property_.availability_confirmed_by_id == actor.pk


def test_touch_owner_updated_sets_timestamp(property_: Property) -> None:
    assert property_.availability_owner_updated_at is None

    PropertyAvailabilityService.touch_owner_updated(property_)

    property_.refresh_from_db()
    assert property_.availability_owner_updated_at is not None


def test_confirm_does_not_bump_updated_at(property_: Property, actor: User) -> None:
    original_updated_at = property_.updated_at

    PropertyAvailabilityService.confirm(property_, actor=actor)

    property_.refresh_from_db()
    assert property_.updated_at == original_updated_at
    assert property_.availability_owner_updated_at is None  # confirm touches only Signal 3


def test_touch_owner_updated_does_not_bump_updated_at(property_: Property) -> None:
    original_updated_at = property_.updated_at

    PropertyAvailabilityService.touch_owner_updated(property_)

    property_.refresh_from_db()
    assert property_.updated_at == original_updated_at
    assert property_.availability_confirmed_at is None  # touch leaves Signal 3 alone


def test_confirm_advances_on_second_call(property_: Property, actor: User) -> None:
    PropertyAvailabilityService.confirm(property_, actor=actor)
    property_.refresh_from_db()
    first = property_.availability_confirmed_at
    assert first is not None

    PropertyAvailabilityService.confirm(property_, actor=actor)
    property_.refresh_from_db()
    second = property_.availability_confirmed_at
    assert second is not None
    assert second >= first
