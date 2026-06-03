"""seed_dev produces a loginable Kostas Hospitality owner fixture."""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import authenticate
from django.core.management import call_command

from owners.enums import OwnerMembershipStatus, OwnerRole
from owners.models import OwnerMembership, OwnerOrganisation, OwnerOrgProperty

pytestmark = pytest.mark.django_db


def _seed() -> None:
    call_command(
        "seed_dev",
        "--properties",
        "4",
        "--bookings",
        "8",
        "--profile",
        "happy",
        "--seed",
        "1",
        stdout=StringIO(),
    )


def test_seed_builds_loginable_owner_with_grants() -> None:
    _seed()

    org = OwnerOrganisation.objects.get(name="Kostas Hospitality Ltd")
    membership = OwnerMembership.objects.get(organisation=org)
    assert membership.role == OwnerRole.ADMIN
    assert membership.status == OwnerMembershipStatus.ACTIVE

    # The owner can actually authenticate.
    user = authenticate(username="andreas.kostas@example.com", password="seed-password")
    assert user is not None
    assert user.pk == membership.user_id

    grants = OwnerOrgProperty.objects.filter(organisation=org, end_date__isnull=True)
    assert grants.count() >= 1
    # At least one property is fully visible so redaction is demoable.
    assert grants.filter(view_full_money=True).exists()
    # And at least one stays hidden (default opt-in) when enough villas exist.
    assert grants.filter(view_full_money=False).exists()


def test_seed_is_idempotent_for_owner_fixture() -> None:
    _seed()
    _seed()

    assert OwnerOrganisation.objects.filter(name="Kostas Hospitality Ltd").count() == 1
    org = OwnerOrganisation.objects.get(name="Kostas Hospitality Ltd")
    # One membership, no duplicate grants per property.
    assert OwnerMembership.objects.filter(organisation=org).count() == 1
    active_grants = OwnerOrgProperty.objects.filter(organisation=org, end_date__isnull=True)
    property_ids = list(active_grants.values_list("property_id", flat=True))
    assert len(property_ids) == len(set(property_ids))
