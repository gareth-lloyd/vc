"""Tests for the `is_assignable_operator` boundary predicate.

The predicate names the "assignable operator" rule the enquiry/booking
assignee guards enforce server-side: an *active staff user with an operator
role* (ADMIN or RESERVATIONS). It is the single source of truth shared by
`IsReservationsWriter` (write floor) and the FE operator picker; the API
boundary depends on it so a hand-rolled request can't set a non-staff user
(e.g. a portal owner) as the salesperson.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser

from accounts.models import User
from core.api.permissions import (
    ASSIGNABLE_STAFF_ROLES,
    effective_staff_role,
    is_assignable_operator,
)
from core.enums import StaffRole

pytestmark = pytest.mark.django_db


def _user(**kwargs: object) -> User:
    defaults: dict[str, object] = {
        "email": kwargs.pop("email", "u@example.com"),
        "is_active": True,
        "is_staff": True,
        "is_superuser": False,
        "role": StaffRole.RESERVATIONS.value,
    }
    defaults.update(kwargs)
    return User.objects.create(**defaults)


def test_staff_admin_is_assignable() -> None:
    assert is_assignable_operator(_user(role=StaffRole.ADMIN.value)) is True


def test_staff_reservations_is_assignable() -> None:
    assert is_assignable_operator(_user(role=StaffRole.RESERVATIONS.value)) is True


def test_staff_accounts_is_not_assignable() -> None:
    assert is_assignable_operator(_user(role=StaffRole.ACCOUNTS.value)) is False


def test_staff_viewer_is_not_assignable() -> None:
    assert is_assignable_operator(_user(role=StaffRole.VIEWER.value)) is False


def test_non_staff_with_admin_role_is_not_assignable() -> None:
    # The Andreas case: an owner-portal user hand-bumped to role=admin but
    # still is_staff=False must not be assignable.
    user = _user(is_staff=False, role=StaffRole.ADMIN.value)
    assert is_assignable_operator(user) is False


def test_inactive_staff_admin_is_not_assignable() -> None:
    assert is_assignable_operator(_user(is_active=False, role=StaffRole.ADMIN.value)) is False


def test_superuser_with_viewer_role_is_assignable() -> None:
    # Superuser resolves to ADMIN regardless of the stored role.
    user = _user(is_superuser=True, role=StaffRole.VIEWER.value)
    assert is_assignable_operator(user) is True


def test_none_is_not_assignable() -> None:
    assert is_assignable_operator(None) is False


def test_anonymous_user_is_not_assignable() -> None:
    assert is_assignable_operator(AnonymousUser()) is False


def test_effective_staff_role_resolves_operator_set() -> None:
    assert ASSIGNABLE_STAFF_ROLES == frozenset(
        {StaffRole.ADMIN.value, StaffRole.RESERVATIONS.value}
    )
    admin = _user(email="admin@example.com", role=StaffRole.ADMIN.value)
    assert effective_staff_role(admin) == StaffRole.ADMIN.value
    assert effective_staff_role(_user(email="owner@example.com", is_staff=False)) is None
    assert effective_staff_role(None) is None
