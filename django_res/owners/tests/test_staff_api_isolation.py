"""An owner (non-staff ``User``) must not reach the staff API surface.

Regression for the multi-tenant auth hole: ``User.role`` defaults to
``StaffRole.VIEWER`` for *every* user, so before the ``IsStaff`` floor an
owner — a perfectly ordinary authenticated ``User`` — could read the entire
staff API (bookings, properties, contacts, payments, guests, …). The staff
API conflated "authenticated" with "staff".

The contract this pins:

* A non-staff owner is **403** on every staff endpoint, whether the endpoint
  is gated by a role class (``IsReservationsWriter``) or by a bare
  ``IsStaff`` floor.
* A real staff user keeps full access.
* The owner portal (``/owner/*``) still works for the owner and stays closed
  to staff-non-owners.
"""

from __future__ import annotations

from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from accounts.models import User
from core.enums import StaffRole
from owners.enums import OwnerMembershipStatus, OwnerRole
from owners.factories import OwnerMembershipFactory
from owners.models import OwnerMembership

pytestmark = pytest.mark.django_db

# Representative staff endpoints. The first group is gated by role classes
# (fixed by hardening ``_user_role``); the second by a bare ``IsAuthenticated``
# that should have been a staff floor.
STAFF_GET_ENDPOINTS = [
    "/api/v1/bookings",
    "/api/v1/properties",
    "/api/v1/enquiries",
    "/api/v1/contacts",
    "/api/v1/payments",
    "/api/v1/guests",
    "/api/v1/roles",
]


def _owner() -> User:
    membership = cast(
        OwnerMembership,
        OwnerMembershipFactory(
            role=OwnerRole.ADMIN,
            status=OwnerMembershipStatus.ACTIVE,
            # A real owner is a non-staff User carrying the model's defaulted
            # VIEWER role — UserFactory otherwise mints staff users.
            user__is_staff=False,
            user__role=StaffRole.VIEWER,
        ),
    )
    # An owner is an ordinary, non-staff User who nonetheless carries the
    # model's defaulted VIEWER role — the exact shape that leaked.
    user = membership.user
    assert user.is_staff is False
    assert user.role == StaffRole.VIEWER
    return user


def _staff() -> User:
    return cast(User, UserFactory(is_staff=True, role=StaffRole.RESERVATIONS))


@pytest.mark.parametrize("path", STAFF_GET_ENDPOINTS)
def test_owner_is_forbidden_on_staff_endpoints(path: str) -> None:
    client = APIClient()
    client.force_authenticate(user=_owner())
    response = client.get(path)
    assert response.status_code == 403, f"{path} leaked to a non-staff owner"


@pytest.mark.parametrize("path", STAFF_GET_ENDPOINTS)
def test_staff_keep_access_to_staff_endpoints(path: str) -> None:
    client = APIClient()
    client.force_authenticate(user=_staff())
    response = client.get(path)
    assert response.status_code != 403, f"{path} wrongly blocked a staff user"


def test_owner_cannot_create_contacts() -> None:
    """The contacts viewset is full CRUD — the write path must be closed too."""
    client = APIClient()
    client.force_authenticate(user=_owner())
    response = client.post("/api/v1/contacts", {"first_name": "X", "last_name": "Y"}, format="json")
    assert response.status_code == 403


def test_owner_portal_still_open_to_owner() -> None:
    client = APIClient()
    client.force_authenticate(user=_owner())
    assert client.get("/api/v1/owner/me").status_code == 200


def test_owner_portal_closed_to_staff_non_owner() -> None:
    client = APIClient()
    client.force_authenticate(user=_staff())
    assert client.get("/api/v1/owner/me").status_code == 403
