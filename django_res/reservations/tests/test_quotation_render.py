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
        enquiry=guest.enquiries.create(),
        guest=guest,
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
        children=1,
        total=Decimal("1234.00"),
        pricing_snapshot={"total": "1234.00"},
    )
    return quotation


@pytest.mark.django_db
def test_build_quotation_context_includes_line_totals(
    priced_quotation: Quotation,
    property_: Property,
) -> None:
    ctx = build_quotation_context(priced_quotation)

    assert ctx["guest_first_name"] == "Ada"
    assert ctx["guest_full_name"] == "Ada Lovelace"
    assert ctx["quotation_reference"] == priced_quotation.reference
    assert "currency_code" not in ctx  # per-line since GAP-014

    assert len(ctx["lines"]) == 1
    line = ctx["lines"][0]
    assert line["currency_code"] == "GBP"
    expected_name = property_.display_name or property_.name
    assert line["property_name"] == expected_name
    assert line["nights"] == 7
    assert line["adults"] == 2
    assert line["children"] == 1
    # Formatted as a thousands-grouped 2-dp string.
    assert line["total"] == "1,234.00"

    assert "terms_html" in ctx


@pytest.mark.django_db
def test_build_quotation_context_has_no_summed_total(
    priced_quotation: Quotation,
    property_: Property,
    gbp: Currency,
) -> None:
    """Lines are alternative villa options the guest picks ONE of, so a
    combined total across them is misleading. Mirrors the quote-builder cart,
    which dropped its summed "Subtotal" for the same reason."""
    QuotationLine.objects.create(
        quotation=priced_quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        adults=2,
        total=Decimal("1000.00"),
        pricing_snapshot={"total": "1000.00"},
    )
    ctx = build_quotation_context(priced_quotation)

    assert len(ctx["lines"]) == 2
    assert [line["total"] for line in ctx["lines"]] == ["1,234.00", "1,000.00"]
    assert "grand_total" not in ctx

    html = render_quotation_html(priced_quotation)
    assert "2,234.00" not in html  # no summed figure anywhere
    assert "Total:" not in html  # no combined-total footer row


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
def test_render_quotation_html_applies_overrides(
    priced_quotation: Quotation,
) -> None:
    """`render_quotation_html` threads operator overrides into the HTML so the
    preview reflects the same copy the email will dispatch."""
    html = render_quotation_html(priced_quotation, intro="A bespoke preview intro.")
    assert "A bespoke preview intro." in html
    assert DEFAULT_INTRO not in html


@pytest.mark.django_db
def test_blank_subject_override_coerced_to_default(
    priced_quotation: Quotation,
) -> None:
    """An empty-string subject (operator cleared the field) must NOT produce a
    blank email subject — it coerces to the non-blank default."""
    ctx = build_quotation_context(priced_quotation, subject="")
    assert ctx["subject"] == f"Your quotation {priced_quotation.reference}"
    assert ctx["subject"].strip()

    ctx_ws = build_quotation_context(priced_quotation, subject="   ")
    assert ctx_ws["subject"] == f"Your quotation {priced_quotation.reference}"


@pytest.mark.django_db
def test_blank_intro_override_respected_as_empty(
    priced_quotation: Quotation,
) -> None:
    """An empty-string intro is a legitimate 'no intro paragraph' — keep it,
    don't fall back to the default (only `subject` coerces blank→default)."""
    ctx = build_quotation_context(priced_quotation, intro="", signoff="")
    assert ctx["intro"] == ""
    assert ctx["signoff"] == ""


@pytest.mark.django_db
def test_hero_image_url_is_absolute_in_render_seam(
    priced_quotation: Quotation,
    property_: Property,
) -> None:
    """The render seam embeds the hero image as `<img src>` in copy-to-Outlook
    HTML and a sandboxed (null-origin) preview iframe, where a host-relative
    `/media/...` src can't resolve. The render-seam URL must be absolute."""
    from django.conf import settings
    from django.core.files.uploadedfile import SimpleUploadedFile

    from properties.enums import ImageKind
    from properties.models import PropertyImage

    PropertyImage.objects.create(
        property=property_,
        kind=ImageKind.HERO,
        image=SimpleUploadedFile("hero.jpg", b"x", content_type="image/jpeg"),
    )

    ctx = build_quotation_context(priced_quotation)
    hero_url = ctx["lines"][0]["hero_image_url"]
    assert hero_url is not None
    assert hero_url.startswith(("http://", "https://"))
    assert hero_url.startswith(settings.FRONTEND_URL.rstrip("/"))

    html = render_quotation_html(priced_quotation)
    assert f'src="{hero_url}"' in html


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


@pytest.mark.django_db
def test_mixed_currency_lines_each_render_their_own_code(
    priced_quotation: Quotation,
    property_: Property,
) -> None:
    """Legacy quote emails freely mixed £/€/$ across options (GAP-014) — each
    line renders its own currency code, in the context and in the HTML."""
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    QuotationLine.objects.create(
        quotation=priced_quotation,
        property=property_,
        currency=eur,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        adults=2,
        total=Decimal("2000.00"),
        pricing_snapshot={"total": "2000.00"},
    )

    ctx = build_quotation_context(priced_quotation)
    assert [line["currency_code"] for line in ctx["lines"]] == ["GBP", "EUR"]

    html = render_quotation_html(priced_quotation)
    assert "GBP 1,234.00" in html
    assert "EUR 2,000.00" in html
