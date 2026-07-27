"""Smoke test for the `zoho_send_sample` ops command (GAP-082 Unit 5).

Not a behaviour suite (the command is an ops sampling utility, exercised
manually against staging) — this pins the picker querysets' field names so a
model rename fails in CI instead of at the ops console.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from typing import cast

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts.enums import ContactRole
from accounts.factories import OrganisationFactory, PersonFactory
from accounts.models import Person
from pricing.models import Currency
from properties.factories import (
    FeatureFactory,
    PropertyContactAssignmentFactory,
    PropertyFactory,
    RoomFactory,
)
from properties.models.features import Feature, PropertyFeature
from properties.models.property import Property
from reservations.factories import EnquiryFactory, TermsVersionFactory, make_occupying_booking
from reservations.models import TermsVersion

pytestmark = pytest.mark.django_db


def test_dry_run_picks_each_kind_without_pushing() -> None:
    prop = cast(Property, PropertyFactory())
    RoomFactory(property=prop)
    PropertyFeature.objects.create(property=prop, feature=cast(Feature, FeatureFactory()))
    PropertyContactAssignmentFactory(property=prop, contact=PersonFactory(), role=ContactRole.OWNER)
    PropertyContactAssignmentFactory(
        property=prop,
        contact=None,
        organisation=OrganisationFactory(),
        role=ContactRole.MANAGEMENT_COMPANY,
    )
    EnquiryFactory(property=prop)
    booking = make_occupying_booking(
        property=prop,
        person=cast(Person, PersonFactory()),
        currency=Currency.objects.get_or_create(
            code="GBP", defaults={"name": "Pound sterling", "symbol": "£"}
        )[0],
        terms=cast(TermsVersion, TermsVersionFactory(version="ss-2026")),
        date_from=timezone.now().date() + timedelta(days=30),
        date_to=timezone.now().date() + timedelta(days=37),
    )

    out = StringIO()
    call_command("zoho_send_sample", "--dry-run", stdout=out)
    output = out.getvalue()

    assert f"[villa] picked pk={prop.pk}" in output
    assert "[contact] picked" in output
    assert "[enquiry] picked" in output
    assert f"[booking] picked pk={booking.pk}" in output
    assert "dry run — nothing pushed" in output
