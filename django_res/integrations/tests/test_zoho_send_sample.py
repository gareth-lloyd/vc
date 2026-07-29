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
from django.core.management import CommandError, call_command
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


# --- --person-pk (GAP-085 fold-in) ----------------------------------------
#
# Limitless needs ONE live contact post with relationships/tags/agency
# populated to finish the Zoho-side field mapping; the richness picker
# prefers-but-relaxes those (reported, but not forceable per-requirement),
# so the curated contact must be selectable deliberately.


def test_person_pk_overrides_the_richness_picker() -> None:
    # Rival sorts first (Person.Meta orders by last_name) AND ties on every
    # optional scalar — without the flag the picker would select it, so this
    # test genuinely fails if --person-pk were ignored.
    PersonFactory(first_name="Rich", last_name="Aardvark")
    target = cast(Person, PersonFactory(first_name="Greg", last_name="Curated"))

    out = StringIO()
    call_command("zoho_send_sample", "--dry-run", "--person-pk", str(target.pk), stdout=out)
    output = out.getvalue()

    assert f"[contact] picked pk={target.pk}" in output
    # The empty-optional-fields report (the command's "what this sample does
    # NOT demonstrate" contract) must still fire for a direct pick.
    assert "empty optional fields:" in output


def test_person_pk_unknown_raises() -> None:
    with pytest.raises(CommandError, match="no Person with that pk"):
        call_command("zoho_send_sample", "--dry-run", "--person-pk", "999999")


def test_person_pk_anonymized_raises() -> None:
    """An anonymized contact would 'succeed' while pushing nothing — the
    payload fails closed to null and the contacts push drops it. Refuse
    loudly instead."""
    person = cast(Person, PersonFactory())
    person.anonymize()

    with pytest.raises(CommandError, match="ANONYMIZED"):
        call_command("zoho_send_sample", "--dry-run", "--person-pk", str(person.pk))
