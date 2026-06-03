"""Constraint + default-flag tests for the owners models."""

from __future__ import annotations

import datetime
from typing import cast

import pytest
from django.db import IntegrityError, transaction

from accounts.factories import UserFactory
from accounts.models import User
from owners.enums import OwnerMembershipStatus, OwnerOrgStatus, OwnerRole
from owners.factories import (
    OwnerMembershipFactory,
    OwnerOrganisationFactory,
    OwnerOrgPropertyFactory,
)
from owners.models import OwnerMembership, OwnerOrganisation, OwnerOrgProperty
from properties.factories import PropertyFactory
from properties.models import Property

pytestmark = pytest.mark.django_db


def test_org_defaults_to_active() -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    assert org.status == OwnerOrgStatus.ACTIVE


def test_grant_visibility_flags_default_hidden() -> None:
    """Q-015: new grants are opt-in — neither money nor guest contact visible."""
    grant = cast(OwnerOrgProperty, OwnerOrgPropertyFactory())
    assert grant.view_full_money is False
    assert grant.view_guest_details is False


def test_membership_defaults_to_pending_admin() -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    membership = OwnerMembership.objects.create(organisation=org, user=cast(User, UserFactory()))
    assert membership.status == OwnerMembershipStatus.PENDING
    assert membership.role == OwnerRole.ADMIN


def test_one_active_grant_per_org_property() -> None:
    grant = cast(OwnerOrgProperty, OwnerOrgPropertyFactory())
    with pytest.raises(IntegrityError), transaction.atomic():
        OwnerOrgProperty.objects.create(
            organisation=grant.organisation,
            property=grant.property,
        )


def test_ended_grant_does_not_block_a_new_active_grant() -> None:
    """A closed grant (end_date set) frees the (org, property) pair to be re-granted."""
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    prop = cast(Property, PropertyFactory())
    OwnerOrgPropertyFactory(organisation=org, property=prop, end_date=datetime.date(2020, 1, 1))
    # Should not raise — the partial unique constraint only covers open grants.
    OwnerOrgPropertyFactory(organisation=org, property=prop)
    assert OwnerOrgProperty.objects.filter(organisation=org, property=prop).count() == 2


def test_unique_membership_per_org_user() -> None:
    membership = cast(OwnerMembership, OwnerMembershipFactory())
    with pytest.raises(IntegrityError), transaction.atomic():
        OwnerMembership.objects.create(
            organisation=membership.organisation,
            user=membership.user,
        )


def test_grant_create_does_not_crash_audit() -> None:
    """Regression: audit must track FK *_id scalars, not un-serialisable FK objects."""
    # A bare create exercises the pre_save audit handler; if it tried to JSON-encode
    # the OwnerOrganisation / Property instances it would raise TypeError here.
    OwnerOrgPropertyFactory()
    OwnerMembershipFactory()
