"""The booking-confirmation email itemises the booking's charge lines (GAP-018).

Legacy `VillaBookingDetail` lines were itemised in the confirmation email; the
rebuild restores that. The rendered HTML (and its derived plaintext) must show
the snapshot base, each positive charge, a separate "Discounts" block for
credits, and a grand total equal to what the guest is scheduled to pay. A
booking with no charge items renders exactly as before — the block is gated.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from comms.management.commands.seed_email_templates import sync_templates
from comms.models import EmailLog, SmtpProfile
from comms.signals import booking_transitioned_handler
from pricing.models import Currency
from properties.models import Property
from reservations.enums import BookingStatus
from reservations.factories import BookingChargeItemFactory, make_occupying_booking
from reservations.models import Booking, Guest, TermsVersion


@pytest.fixture
def gbp(db: None) -> Currency:
    return Currency.objects.create(code="GBP", name="Pound sterling", symbol="£")


@pytest.fixture
def guest(db: None) -> Guest:
    return Guest.objects.create(first_name="Ada", last_name="Lovelace", email="ada@example.com")


@pytest.fixture
def terms(db: None) -> TermsVersion:
    return TermsVersion.objects.create(
        version="2026-01",
        body_markdown="**T&Cs**",
        published_at=timezone.now(),
        is_current=True,
    )


@pytest.fixture
def property_(db: None) -> Property:
    from properties.models import Country, PropertyCategory, PropertyGroup, Region

    country, _ = Country.objects.get_or_create(
        iso2="GB", defaults={"name": "United Kingdom", "iso3": "GBR"}
    )
    region = Region.objects.create(country=country, name="South West", slug="south-west")
    category = PropertyCategory.objects.create(name="Villa", slug="villa")
    group = PropertyGroup.objects.create(name="Test group")
    return Property.objects.create(
        name="Test Villa",
        display_name="Test Villa",
        slug="test-villa",
        category=category,
        group=group,
        region=region,
    )


def _build_booking(
    *,
    property_: Property,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    with_charges: bool,
) -> Booking:
    booking = make_occupying_booking(
        property=property_,
        guest=guest,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    booking.pricing_snapshot = {"total": "1400.00"}
    booking.save(update_fields=["pricing_snapshot"])
    if with_charges:
        BookingChargeItemFactory(
            booking=booking, currency=gbp, label="Late checkout", amount=Decimal("150.00")
        )
        BookingChargeItemFactory(
            booking=booking, currency=gbp, label="Heli transfer", amount=Decimal("900.00")
        )
        BookingChargeItemFactory(
            booking=booking, currency=gbp, label="Loyalty credit", amount=Decimal("-500.00")
        )
    return booking


def _fire_confirmation(booking: Booking) -> EmailLog:
    booking_transitioned_handler(
        sender=Booking,
        from_status=BookingStatus.PENDING_OWNER_APPROVAL.value,
        to_status=BookingStatus.AWAITING_DEPOSIT.value,
        booking=booking,
    )
    return EmailLog.objects.get(template_key="booking.confirmation")


@pytest.mark.django_db
def test_confirmation_itemises_charges_and_discounts(
    system_profile: SmtpProfile,
    property_: Property,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    sync_templates()
    booking = _build_booking(
        property_=property_, guest=guest, gbp=gbp, terms=terms, with_charges=True
    )

    log = _fire_confirmation(booking)
    html = log.rendered_body_html

    # Snapshot base line.
    assert "GBP 1,400.00" in html
    # Positive charges, each on its own line.
    assert "Late checkout" in html
    assert "GBP 150.00" in html
    assert "Heli transfer" in html
    assert "GBP 900.00" in html
    # Credits surface under a separate "Discounts" block (the GAP-018 decision).
    assert "Discounts" in html
    assert "Loyalty credit" in html
    assert "-500.00" in html
    # Grand total = 1400 + 150 + 900 - 500, byte-equal to the scheduled total.
    assert "GBP 1,950.00" in html
    # The derived plaintext alternative carries the itemisation too.
    assert "Late checkout" in log.rendered_body
    assert "Loyalty credit" in log.rendered_body


@pytest.mark.django_db
def test_confirmation_without_charges_omits_the_block(
    system_profile: SmtpProfile,
    property_: Property,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    sync_templates()
    booking = _build_booking(
        property_=property_, guest=guest, gbp=gbp, terms=terms, with_charges=False
    )

    log = _fire_confirmation(booking)
    html = log.rendered_body_html

    # No charge items → the itemisation block is gated out entirely; the email
    # renders exactly as it did before GAP-018. Assert the whole block is gone
    # (base label, Discounts heading, AND the base/total figure) so a future
    # refactor can't leave an orphan Total/subtotal row outside the `{% if %}`.
    assert "Booking subtotal" not in html
    assert "Discounts" not in html
    assert "GBP 1,400.00" not in html
    # The existing confirmation copy is unaffected.
    assert "confirmed" in html.lower()
