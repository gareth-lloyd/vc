"""factory-boy factories for the `reservations` app.

`Quotation` / `QuotationLine` / `Booking` are deliberately *not* factories:
they are created through the service layer (`QuotationService`,
`BookingService`) by the `seed_dev` command so statuses, events, holds and
pricing snapshots stay production-faithful.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import factory
from django.db import transaction
from django.utils import timezone
from factory.django import DjangoModelFactory

from accounts.factories import CustomerPersonFactory
from core.factories import RUN_TOKEN
from properties.factories import PropertyFactory
from reservations import models
from reservations.enums import (
    BookingGuestRole,
    BookingNoteKind,
    BookingNoteVisibility,
    BookingStatus,
    ConciergeService,
    EnquiryNoteKind,
    EnquiryRequestType,
    EnquiryStatus,
    PaymentMethod,
    ServiceStatus,
)

if TYPE_CHECKING:
    from accounts.models import Person
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import Booking, TermsVersion


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

    # GAP-045 D5-1: `Enquiry.person` is nullable, but tests overwhelmingly expect
    # a customer attached, so default to a CUSTOMER Person (override `person=` or
    # pass `person=None` for the anonymous-enquiry case).
    person = factory.SubFactory(CustomerPersonFactory)
    property = factory.SubFactory(PropertyFactory)
    date_from = factory.LazyFunction(lambda: date.today() + timedelta(days=30))
    date_to = factory.LazyFunction(lambda: date.today() + timedelta(days=37))
    adults = 2
    children = 0
    request_type = EnquiryRequestType.QUOTE
    status = EnquiryStatus.NEW
    inbound_message = factory.Faker("sentence")


class EnquiryNoteFactory(DjangoModelFactory):
    """Operator-authored note on an Enquiry. `author` defaults to NULL so the
    factory doesn't pull in `accounts` and bloat the dependency graph."""

    class Meta:
        model = models.EnquiryNote

    enquiry = factory.SubFactory(EnquiryFactory)
    author = None
    kind = EnquiryNoteKind.GENERAL
    body = factory.Faker("sentence")
    is_pinned = False


class BookingGuestFactory(DjangoModelFactory):
    """Attach a customer Person to a Booking under a role. Caller supplies
    `booking=` (Booking is service-built, so it has no sensible default); the
    customer `person=` defaults to a fresh CUSTOMER Person but is usually
    overridden with the booking's lead customer."""

    class Meta:
        model = models.BookingGuest

    booking = None  # required: provided by caller
    # GAP-045 Unit 3d-A: `person` is the NOT-NULL authoritative customer FK.
    person = factory.SubFactory(CustomerPersonFactory)
    role = BookingGuestRole.CO_TRAVELLER
    email_override = ""
    notes = ""


class BookingNoteFactory(DjangoModelFactory):
    """Operator-authored note on a Booking. Caller must supply `booking=` —
    `Booking` rows are built through the service layer rather than a factory,
    so there is no SubFactory default to lean on."""

    class Meta:
        model = models.BookingNote

    booking = None  # required: provided by caller
    author = None
    kind = BookingNoteKind.GENERAL
    visibility = BookingNoteVisibility.STAFF_ONLY
    body = factory.Faker("sentence")
    is_pinned = False


class BookingChargeItemFactory(DjangoModelFactory):
    """Manual charge/credit line on a Booking. Caller must supply `booking=`
    and `currency=` (`Booking` rows are service-built, and the currency must
    match the booking's, so neither has a SubFactory default)."""

    class Meta:
        model = models.BookingChargeItem

    booking = None  # required: provided by caller
    label = factory.Faker("sentence", nb_words=3)
    amount = Decimal("100.00")
    currency = None  # required: provided by caller (must equal booking.currency)
    notes = ""


class BookingServiceCoverageFactory(DjangoModelFactory):
    """One concierge coverage cell on a Booking. Caller must supply `booking=`
    (`Booking` rows are service-built, so there is no SubFactory default).
    `(booking, service)` is unique — vary `service` when building several."""

    class Meta:
        model = models.BookingServiceCoverage

    booking = None  # required: provided by caller
    service = ConciergeService.CHEF
    status = ServiceStatus.NOT_STARTED
    notes = ""


def make_occupying_booking(
    *,
    property: Property,
    person: Person,
    currency: Currency,
    terms: TermsVersion,
    date_from: date,
    date_to: date,
    adults: int = 2,
) -> Booking:
    """Fabricate an *occupying* Booking (Quotation → line → Booking → LEAD
    BookingGuest) without the full `BookingService` lifecycle.

    Conflict/ingest scenarios — the iCal demo command and `ICalIngestService`
    tests — only need a booking that occupies a date range to trip the overlap
    guards, not the submit / auto-accept / payment-schedule flow. This is the
    one place that shape is built, so the load-bearing LEAD `BookingGuest`
    invariant (`django_res/CLAUDE.md`) is encoded once instead of by hand in
    each caller. Everything links back to `person` (the customer), so a
    relationship-driven teardown (the demo `--reset`) unwinds it cleanly.
    """
    quotation = models.Quotation.objects.create(
        enquiry=models.Enquiry.objects.create(
            person=person,
            property=property,
            date_from=date_from,
            date_to=date_to,
        ),
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = models.QuotationLine.objects.create(
        quotation=quotation,
        property=property,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
        adults=adults,
        total=Decimal("1400.00"),
    )
    with transaction.atomic():
        booking = models.Booking.objects.create(
            quotation_line=line,
            person=person,
            property=property,
            date_from=date_from,
            date_to=date_to,
            adults=adults,
            currency=currency,
            terms_version=terms,
            terms_accepted_at=timezone.now(),
            payment_method=PaymentMethod.CARD.value,
            status=BookingStatus.AWAITING_DEPOSIT.value,
        )
        # The LEAD BookingGuest invariant — a Booking is incomplete without it.
        models.BookingGuest.objects.get_or_create(
            booking=booking,
            person=person,
            defaults={"role": BookingGuestRole.LEAD.value},
        )
    return booking
