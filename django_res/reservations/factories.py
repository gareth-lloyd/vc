"""factory-boy factories for the `reservations` app.

`Quotation` / `QuotationLine` / `Booking` are deliberately *not* factories:
they are created through the service layer (`QuotationService`,
`BookingService`) by the `seed_dev` command so statuses, events, holds and
pricing snapshots stay production-faithful.
"""

from __future__ import annotations

from datetime import date, timedelta

import factory
from factory.django import DjangoModelFactory

from properties.factories import RUN_TOKEN, CountryFactory, PropertyFactory
from reservations import models
from reservations.enums import EnquiryRequestType, EnquiryStatus


class GuestFactory(DjangoModelFactory):
    class Meta:
        model = models.Guest

    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.Sequence(lambda n: f"guest-{RUN_TOKEN}-{n}@example.com")
    phone = factory.Sequence(lambda n: f"+44 7700 1{n:05d} x{RUN_TOKEN}")
    country = factory.SubFactory(CountryFactory)
    marketing_consent = factory.Iterator([True, False])


class TermsVersionFactory(DjangoModelFactory):
    class Meta:
        model = models.TermsVersion
        django_get_or_create = ("version",)

    version = factory.Sequence(lambda n: f"terms-{RUN_TOKEN}-{n}")
    body_markdown = "## Booking terms\n\nStandard villa rental terms apply."
    # `only_one_current_terms_version` is a partial unique constraint, so the
    # factory must default to False; the seeder calls `.publish()` on one.
    is_current = False


class EnquiryFactory(DjangoModelFactory):
    class Meta:
        model = models.Enquiry

    guest = factory.SubFactory(GuestFactory)
    property = factory.SubFactory(PropertyFactory)
    date_from = factory.LazyFunction(lambda: date.today() + timedelta(days=30))
    date_to = factory.LazyFunction(lambda: date.today() + timedelta(days=37))
    adults = 2
    children = 0
    request_type = EnquiryRequestType.QUOTE
    status = EnquiryStatus.NEW
    inbound_message = factory.Faker("sentence")
