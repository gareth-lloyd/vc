"""GAP-045 Unit 3a — the parallel customer ``person`` FK on the five
reservations models that currently carry a ``guest`` FK.

This is the additive ("expand") half of an expand/contract migration: the FK
exists and is nullable everywhere, but nothing reads or writes it yet (that is
Unit 3c). These tests pin the schema shape so the cutover has a stable base.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from django.db import models

from accounts.factories import PersonFactory
from accounts.models import Person
from reservations.factories import EnquiryFactory
from reservations.models import (
    Booking,
    BookingGuest,
    Enquiry,
    GuestPreference,
    Quotation,
)

# (model, on_delete mirrored from guest, final reverse accessor on Person)
PERSON_FK_SPECS = [
    (Enquiry, models.SET_NULL, "enquiries_as_customer"),
    (Quotation, models.PROTECT, "quotations_as_customer"),
    (Booking, models.PROTECT, "bookings_as_customer"),
    (BookingGuest, models.PROTECT, "booking_guests"),
    (GuestPreference, models.CASCADE, "travel_preferences"),
]


@pytest.mark.parametrize(("model", "on_delete", "related_name"), PERSON_FK_SPECS)
def test_person_fk_schema(model: type[models.Model], on_delete: Any, related_name: str) -> None:
    field = model._meta.get_field("person")
    assert isinstance(field, models.ForeignKey)
    related = cast("type[models.Model]", field.related_model)
    assert related._meta.label == "accounts.Person"
    # Nullable everywhere during expand/contract, even where the parallel
    # ``guest`` FK is non-null (Quotation/Booking/BookingGuest are PROTECT).
    assert field.null is True
    assert field.blank is True
    # on_delete mirrors the guest FK it shadows.
    assert field.remote_field.on_delete is on_delete
    # Final (post-retirement) names chosen now so Unit 3d is a model removal,
    # not a related_name rename.
    assert field.remote_field.related_name == related_name


@pytest.mark.django_db
def test_person_fk_nullable_and_round_trips() -> None:
    # Enquiry.person is nullable (SET_NULL — anonymous enquiries have no
    # customer). Build one explicitly without a guest so person starts None,
    # then point it and assert the round-trip + reverse accessor.
    enquiry = Enquiry.objects.create(first_name="Anon", last_name="Lead")
    assert enquiry.person is None

    person = cast(Person, PersonFactory())
    enquiry.person = person
    enquiry.save(update_fields=["person"])

    enquiry.refresh_from_db()
    assert enquiry.person == person
    assert list(person.enquiries_as_customer.all()) == [enquiry]


@pytest.mark.django_db
def test_enquiry_factory_populates_person_mirror() -> None:
    # GAP-045 Unit 3d-3: factory-built rows mirror production, where every
    # customer-linked row carries the Person (reads resolve solely from it).
    enquiry = cast(Enquiry, EnquiryFactory())
    assert enquiry.person is not None
    assert enquiry.person.legacy_id == f"guest-{enquiry.guest_id}"
