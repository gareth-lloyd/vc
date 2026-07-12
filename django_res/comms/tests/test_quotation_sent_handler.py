"""The quotation.sent email must actually contain the quote.

Regression for the content-less stub: the rendered HTML body now carries
the line's property name and its formatted total, sourced from the shared
`build_quotation_context` render seam.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import cast

import pytest
from django.utils import timezone

from accounts.factories import CustomerPersonFactory
from accounts.models import Person
from comms.management.commands.seed_email_templates import sync_templates
from comms.models import EmailLog, SmtpProfile
from comms.signals import quotation_sent_handler
from pricing.models import Currency
from properties.models import Property
from reservations.models import Enquiry, Quotation, QuotationLine, TermsVersion


@pytest.fixture
def gbp(db: None) -> Currency:
    return Currency.objects.create(code="GBP", name="Pound sterling", symbol="£")


@pytest.fixture
def customer(db: None) -> Person:
    return cast(
        Person,
        CustomerPersonFactory(
            first_name="Ada",
            last_name="Lovelace",
            primary_email="ada@example.com",
        ),
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
        Region,
    )

    country, _ = Country.objects.get_or_create(
        iso2="GB",
        defaults={"name": "United Kingdom", "iso3": "GBR"},
    )
    region = Region.objects.create(country=country, name="South West", slug="south-west")
    category = PropertyCategory.objects.create(name="Villa", slug="villa")
    return Property.objects.create(
        name="Test Villa",
        display_name="Test Villa",
        slug="test-villa",
        category=category,
        region=region,
    )


@pytest.fixture
def quotation_with_line(
    db: None,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Quotation:
    quotation = Quotation.objects.create(
        enquiry=Enquiry.objects.create(person=customer, property=property_),
        person=customer,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
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
    # Per-line currency (GAP-014): the template renders each line in its own
    # code — a header-level `currency_code` no longer exists, so a bare total
    # (or "Total ()") means the template drifted from the render context.
    assert "GBP 1,234.00" in log.rendered_body_html
    assert "Total ()" not in log.rendered_body_html
    assert quotation_with_line.reference in log.rendered_subject
    # Plaintext alternative carries the quote too.
    assert expected_name in log.rendered_body
    assert "GBP 1,234.00" in log.rendered_body
    # GAP-078: a single (country, region) group renders NO geo header —
    # a lone label is noise.
    assert "United Kingdom · South West" not in log.rendered_body_html


@pytest.mark.django_db
def test_quotation_sent_email_groups_lines_by_geography(
    system_profile: SmtpProfile,
    quotation_with_line: Quotation,
    gbp: Currency,
) -> None:
    """GAP-078: a multi-country quotation email bunches lines under
    country · region section headers (the single-group no-header case is
    asserted in test_quotation_sent_email_contains_line_and_total)."""
    from properties.models import Country, PropertyCategory, Region

    greece, _ = Country.objects.get_or_create(iso2="GR", defaults={"name": "Greece", "iso3": "GRC"})
    crete = Region.objects.create(country=greece, name="Crete", slug="crete")
    category = PropertyCategory.objects.get(slug="villa")
    zeus = Property.objects.create(
        name="Villa Zeus",
        display_name="Villa Zeus",
        slug="villa-zeus",
        category=category,
        region=crete,
    )
    QuotationLine.objects.create(
        quotation=quotation_with_line,
        property=zeus,
        currency=gbp,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        adults=2,
        total=Decimal("2000.00"),
        pricing_snapshot={"total": "2000.00"},
    )
    sync_templates()

    quotation_sent_handler(sender=Quotation, quotation=quotation_with_line)

    log = EmailLog.objects.get(template_key="quotation.sent")
    body = log.rendered_body_html
    greece_at = body.index("Greece · Crete")
    uk_at = body.index("United Kingdom · South West")
    assert greece_at < body.index("Villa Zeus") < uk_at
    assert uk_at < body.index("Test Villa")
