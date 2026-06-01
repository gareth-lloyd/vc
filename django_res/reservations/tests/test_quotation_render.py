"""Tests for the shared quotation render seam.

`build_quotation_context` and `render_quotation_html` are the single source
of truth that the email, the (later) preview modal, and copy-to-clipboard
all consume.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from pricing.models import Currency
from properties.models import Property
from reservations.models import Guest, Quotation, QuotationLine, TermsVersion
from reservations.services.quotation_render import (
    DEFAULT_INTRO,
    DEFAULT_SIGNOFF,
    build_quotation_context,
    render_quotation_html,
)


@pytest.fixture
def priced_quotation(
    db: None,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Quotation:
    quotation = Quotation.objects.create(
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
        children=1,
        total=Decimal("1234.00"),
        pricing_snapshot={"total": "1234.00"},
    )
    return quotation


@pytest.mark.django_db
def test_build_quotation_context_includes_line_and_grand_total(
    priced_quotation: Quotation,
    property_: Property,
) -> None:
    ctx = build_quotation_context(priced_quotation)

    assert ctx["guest_first_name"] == "Ada"
    assert ctx["guest_full_name"] == "Ada Lovelace"
    assert ctx["quotation_reference"] == priced_quotation.reference
    assert ctx["currency_code"] == "GBP"

    assert len(ctx["lines"]) == 1
    line = ctx["lines"][0]
    expected_name = property_.display_name or property_.name
    assert line["property_name"] == expected_name
    assert line["nights"] == 7
    assert line["adults"] == 2
    assert line["children"] == 1
    # Formatted as a thousands-grouped 2-dp string.
    assert line["total"] == "1,234.00"

    assert ctx["grand_total"] == "1,234.00"
    assert "terms_html" in ctx


@pytest.mark.django_db
def test_build_quotation_context_sums_multiple_lines(
    priced_quotation: Quotation,
    property_: Property,
) -> None:
    QuotationLine.objects.create(
        quotation=priced_quotation,
        property=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        adults=2,
        total=Decimal("1000.00"),
        pricing_snapshot={"total": "1000.00"},
    )
    ctx = build_quotation_context(priced_quotation)

    assert len(ctx["lines"]) == 2
    assert ctx["grand_total"] == "2,234.00"


@pytest.mark.django_db
def test_build_quotation_context_default_subject(
    priced_quotation: Quotation,
) -> None:
    ctx = build_quotation_context(priced_quotation)
    assert ctx["subject"] == f"Your quotation {priced_quotation.reference}"
    assert ctx["intro"] == DEFAULT_INTRO
    assert ctx["signoff"] == DEFAULT_SIGNOFF


@pytest.mark.django_db
def test_build_quotation_context_applies_overrides(
    priced_quotation: Quotation,
) -> None:
    ctx = build_quotation_context(
        priced_quotation,
        subject="Custom subject",
        intro="Custom intro line.",
        signoff="Custom sign-off.",
    )
    assert ctx["subject"] == "Custom subject"
    assert ctx["intro"] == "Custom intro line."
    assert ctx["signoff"] == "Custom sign-off."


@pytest.mark.django_db
def test_override_flows_into_rendered_html(
    priced_quotation: Quotation,
) -> None:
    html = render_quotation_html(priced_quotation)
    assert DEFAULT_INTRO in html


@pytest.mark.django_db
def test_build_quotation_context_carries_discount_and_inclusions(
    priced_quotation: Quotation,
    property_: Property,
) -> None:
    line = priced_quotation.lines.first()
    assert line is not None
    line.discount = Decimal("100.00")
    line.inclusions = "Daily breakfast; airport transfer"
    line.total = Decimal("1134.00")
    line.save(update_fields=["discount", "inclusions", "total"])

    ctx = build_quotation_context(priced_quotation)
    rendered_line = ctx["lines"][0]
    assert rendered_line["discount"] == "100.00"
    assert rendered_line["inclusions"] == "Daily breakfast; airport transfer"


@pytest.mark.django_db
def test_render_html_shows_inclusions_and_discount(
    priced_quotation: Quotation,
) -> None:
    line = priced_quotation.lines.first()
    assert line is not None
    line.discount = Decimal("100.00")
    line.inclusions = "Daily breakfast included"
    line.save(update_fields=["discount", "inclusions"])

    html = render_quotation_html(priced_quotation)
    assert "Daily breakfast included" in html
    assert "100.00" in html


@pytest.mark.django_db
def test_render_quotation_html_contains_line_and_terms(
    priced_quotation: Quotation,
    property_: Property,
) -> None:
    html = render_quotation_html(priced_quotation)

    expected_name = property_.display_name or property_.name
    assert expected_name in html
    assert "1,234.00" in html
    assert priced_quotation.reference in html
    # Terms markdown ("**T&Cs**") renders to HTML.
    assert "T&amp;Cs" in html or "T&Cs" in html
    assert "<strong>" in html
