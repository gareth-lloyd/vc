"""An owner (non-staff ``User``) must not reach the staff API surface.

Regression for the multi-tenant auth hole: ``User.role`` defaults to
``StaffRole.VIEWER`` for *every* user, so before the ``IsStaff`` floor an
owner — a perfectly ordinary authenticated ``User`` — could read the entire
staff API (bookings, properties, contacts, payments, …). The staff
API conflated "authenticated" with "staff".

The contract this pins:

* A non-staff owner is **403** on every staff endpoint, whether the endpoint
  is gated by a role class (``IsReservationsWriter``) or by a bare
  ``IsStaff`` floor.
* A real staff user keeps full access.
* The owner portal still works for the owner. Its *data* endpoints
  (``/owner/properties``, …) stay ``IsOwner``-closed to staff-non-owners. The
  ``/owner/me`` *probe* is deliberately the exception: it is readable by any
  authenticated user and returns ``{is_owner: false, organisations: []}`` for a
  non-owner (leaking nothing), so the SPA can pick its shell without a 403.
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


def test_owner_me_probe_open_to_staff_non_owner_as_not_owner() -> None:
    # The /owner/me probe drives boot-time shell selection, so it is readable by
    # any authenticated user: a staff non-owner gets 200 + is_owner:false and an
    # empty org list (no leak), rather than the old 403-as-control-flow.
    client = APIClient()
    client.force_authenticate(user=_staff())
    resp = client.get("/api/v1/owner/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_owner"] is False
    assert body["organisations"] == []


def test_owner_data_endpoints_stay_closed_to_staff_non_owner() -> None:
    # The probe relaxing to 200 must NOT widen the owner *data* surface: the
    # IsOwner-gated endpoints stay 403 for a staff non-owner.
    client = APIClient()
    client.force_authenticate(user=_staff())
    assert client.get("/api/v1/owner/properties").status_code == 403
