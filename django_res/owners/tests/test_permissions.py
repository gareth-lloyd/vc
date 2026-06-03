"""Tests for the owner-identity predicate / permission."""

from __future__ import annotations

from typing import cast

import pytest

from accounts.factories import UserFactory
from accounts.models import User
from core.enums import StaffRole
from owners.enums import OwnerMembershipStatus, OwnerOrgStatus
from owners.factories import OwnerMembershipFactory, OwnerOrganisationFactory
from owners.models import OwnerMembership, OwnerOrganisation
from owners.permissions import is_owner

pytestmark = pytest.mark.django_db


def test_active_member_of_active_org_is_owner() -> None:
    membership = cast(OwnerMembership, OwnerMembershipFactory(status=OwnerMembershipStatus.ACTIVE))
    assert is_owner(membership.user) is True


def test_staff_without_membership_is_not_owner() -> None:
    staff = cast(User, UserFactory(role=StaffRole.RESERVATIONS))
    assert is_owner(staff) is False


def test_pending_membership_is_not_owner() -> None:
    membership = cast(OwnerMembership, OwnerMembershipFactory(status=OwnerMembershipStatus.PENDING))
    assert is_owner(membership.user) is False


def test_member_of_suspended_org_is_not_owner() -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory(status=OwnerOrgStatus.SUSPENDED))
    membership = cast(
        OwnerMembership,
        OwnerMembershipFactory(organisation=org, status=OwnerMembershipStatus.ACTIVE),
    )
    assert is_owner(membership.user) is False
