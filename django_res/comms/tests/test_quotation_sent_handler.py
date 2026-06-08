"""The quotation.sent email must actually contain the quote.

Regression for the content-less stub: the rendered HTML body now carries
the line's property name and its formatted total, sourced from the shared
`build_quotation_context` render seam.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from comms.management.commands.seed_email_templates import sync_templates
from comms.models import EmailLog, SmtpProfile
from comms.signals import quotation_sent_handler
from pricing.models import Currency
from properties.models import Property
from reservations.models import Guest, Quotation, QuotationLine, TermsVersion


@pytest.fixture
def gbp(db: None) -> Currency:
    return Currency.objects.create(code="GBP", name="Pound sterling", symbol="£")


@pytest.fixture
def guest(db: None) -> Guest:
    return Guest.objects.create(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
    )


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
    from properties.models import (
        Country,
        PropertyCategory,
        PropertyGroup,
        Region,
    )

    country, _ = Country.objects.get_or_create(
        iso2="GB",
        defaults={"name": "United Kingdom", "iso3": "GBR"},
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


@pytest.fixture
def quotation_with_line(
    db: None,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Quotation:
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1234.00"),
        pricing_snapshot={"total": "1234.00"},
    )
    return quotation


@pytest.mark.django_db
def test_quotation_sent_email_contains_line_and_total(
    system_profile: SmtpProfile,
    quotation_with_line: Quotation,
    property_: Property,
) -> None:
    # Seed the real templates from disk so the handler renders the compiled
    # MJML body (not a test stub).
    sync_templates()

    quotation_sent_handler(sender=Quotation, quotation=quotation_with_line)

    log = EmailLog.objects.get(template_key="quotation.sent")
    expected_name = property_.display_name or property_.name
    assert expected_name in log.rendered_body_html
    assert "1,234.00" in log.rendered_body_html
    assert quotation_with_line.reference in log.rendered_subject
    # Plaintext alternative carries the quote too.
    assert expected_name in log.rendered_body
    assert "1,234.00" in log.rendered_body
