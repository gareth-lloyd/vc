"""Server-side scoping + visibility-merge tests."""

from __future__ import annotations

import datetime
from typing import cast

import pytest

from accounts.factories import UserFactory
from accounts.models import User
from owners.enums import OwnerMembershipStatus, OwnerOrgStatus
from owners.factories import (
    OwnerMembershipFactory,
    OwnerOrganisationFactory,
    OwnerOrgPropertyFactory,
)
from owners.models import OwnerOrganisation
from owners.scoping import owner_property_ids, owner_visibility_map
from properties.factories import PropertyFactory
from properties.models import Property

pytestmark = pytest.mark.django_db


def _new_org(**kwargs: object) -> OwnerOrganisation:
    return cast(OwnerOrganisation, OwnerOrganisationFactory(**kwargs))


def _new_property() -> Property:
    return cast(Property, PropertyFactory())


def _owner_of(org: OwnerOrganisation) -> User:
    user = cast(User, UserFactory())
    OwnerMembershipFactory(organisation=org, user=user, status=OwnerMembershipStatus.ACTIVE)
    return user


def test_scope_returns_only_granted_properties() -> None:
    org = _new_org()
    user = _owner_of(org)
    granted = _new_property()
    OwnerOrgPropertyFactory(organisation=org, property=granted)
    _new_property()  # ungranted villa belonging to nobody

    assert owner_property_ids(user) == {granted.id}


def test_scope_excludes_ended_grants() -> None:
    org = _new_org()
    user = _owner_of(org)
    prop = _new_property()
    OwnerOrgPropertyFactory(organisation=org, property=prop, end_date=datetime.date(2020, 1, 1))
    assert owner_property_ids(user) == set()


def test_scope_excludes_inactive_membership() -> None:
    org = _new_org()
    user = cast(User, UserFactory())
    OwnerMembershipFactory(organisation=org, user=user, status=OwnerMembershipStatus.PENDING)
    OwnerOrgPropertyFactory(organisation=org, property=_new_property())
    assert owner_property_ids(user) == set()


def test_scope_excludes_suspended_org() -> None:
    org = _new_org(status=OwnerOrgStatus.SUSPENDED)
    user = _owner_of(org)
    OwnerOrgPropertyFactory(organisation=org, property=_new_property())
    assert owner_property_ids(user) == set()


def test_visibility_map_carries_per_property_flags() -> None:
    org = _new_org()
    user = _owner_of(org)
    open_prop = _new_property()
    closed_prop = _new_property()
    OwnerOrgPropertyFactory(
        organisation=org, property=open_prop, view_full_money=True, view_guest_details=True
    )
    OwnerOrgPropertyFactory(organisation=org, property=closed_prop)

    vis = owner_visibility_map(user)
    assert vis[open_prop.id] == {"view_full_money": True, "view_guest_details": True}
    assert vis[closed_prop.id] == {"view_full_money": False, "view_guest_details": False}


def test_co_owned_villa_or_merges_most_permissive() -> None:
    """A villa co-owned via two orgs the user belongs to → union of both grants."""
    org_a = _new_org()
    org_b = _new_org()
    user = cast(User, UserFactory())
    OwnerMembershipFactory(organisation=org_a, user=user, status=OwnerMembershipStatus.ACTIVE)
    OwnerMembershipFactory(organisation=org_b, user=user, status=OwnerMembershipStatus.ACTIVE)
    villa = _new_property()
    # org A can see money but not guests; org B the reverse.
    OwnerOrgPropertyFactory(
        organisation=org_a, property=villa, view_full_money=True, view_guest_details=False
    )
    OwnerOrgPropertyFactory(
        organisation=org_b, property=villa, view_full_money=False, view_guest_details=True
    )

    vis = owner_visibility_map(user)
    assert owner_property_ids(user) == {villa.id}
    assert vis[villa.id] == {"view_full_money": True, "view_guest_details": True}
