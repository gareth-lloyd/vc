"""GAP-094 — booking contract render seam + staff HTML preview.

`build_contract_context` / `render_contract_html` / `render_contract_pdf` are
the single source of truth for the guest-facing contract document. The house
rules render from the confirmation-time `house_rules_snapshot`, never the
property's live rules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from core.tests import assert_max_queries
from payments.models import Payment
from properties.enums import DescriptionSection
from properties.models import Property, PropertyDescription
from reservations.enums import BookingStatus
from reservations.services.booking_contract_render import (
    build_contract_context,
    render_contract_html,
    render_contract_pdf,
)
from reservations.services.bookings import BookingService

if TYPE_CHECKING:
    from reservations.models import Booking, QuotationLine, TermsVersion


RULES = "No parties. Quiet after 23:00.\nNo smoking indoors."


def _set_house_rules(property_: Property, body: str) -> PropertyDescription:
    return PropertyDescription.objects.update_or_create(
        property=property_,
        section=DescriptionSection.HOUSE_RULES,
        defaults={"body": body},
    )[0]


@pytest.fixture
def booking(quotation_line: QuotationLine, terms: TermsVersion) -> Booking:
    _set_house_rules(quotation_line.property, RULES)
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    booking.refresh_from_db()
    assert booking.status == BookingStatus.AWAITING_DEPOSIT
    return booking


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="contract-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


# ----------------------------------------------------------------------
# Context
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_build_contract_context_carries_booking_facts(booking: Booking) -> None:
    ctx = build_contract_context(booking)

    assert ctx["booking_reference"] == booking.reference
    assert ctx["property_name"] == "Test Villa"
    assert ctx["region_name"] == "South West"
    assert ctx["country_name"] == "United Kingdom"
    assert ctx["date_from"] == "10 June 2026"
    assert ctx["date_to"] == "17 June 2026"
    assert ctx["nights"] == 7
    assert ctx["guest_full_name"]
    assert ctx["adults"] == 2
    assert ctx["children"] == 0
    assert ctx["breakdown"]["currency"] == "GBP"
    assert ctx["breakdown"]["total"] == "1,400.00"
    assert "<strong>T&amp;Cs</strong>" in ctx["terms_html"]
    assert ctx["terms_accepted_at"]
    # Plain text, verbatim — the template does the wrapping/escaping.
    assert ctx["house_rules"] == RULES
    assert ctx["generated_on"]


@pytest.mark.django_db
def test_context_payment_schedule_lists_guest_facing_rows(booking: Booking) -> None:
    booking.payments.all().delete()
    Payment.objects.create(
        booking=booking,
        purpose="deposit",
        status="pending",
        amount=Decimal("420.00"),
        currency=booking.currency,
        due_at=datetime(2026, 3, 1, 12, tzinfo=UTC),
    )
    Payment.objects.create(
        booking=booking,
        purpose="balance",
        status="succeeded",
        amount=Decimal("980.00"),
        currency=booking.currency,
        due_at=datetime(2026, 5, 1, 12, tzinfo=UTC),
    )
    # Non-guest-facing / nothing-owed rows are ignored.
    Payment.objects.create(
        booking=booking,
        purpose="security_deposit",
        status="pending",
        amount=Decimal("500.00"),
        currency=booking.currency,
    )
    for status in ("cancelled", "expired", "failed", "waived", "refunded"):
        Payment.objects.create(
            booking=booking,
            purpose="deposit",
            status=status,
            amount=Decimal("999.00"),
            currency=booking.currency,
        )

    schedule = build_contract_context(booking)["payment_schedule"]

    assert schedule == [
        {"label": "Deposit", "amount": "420.00", "due_at": "1 March 2026", "is_paid": False},
        {"label": "Balance", "amount": "980.00", "due_at": "1 May 2026", "is_paid": True},
    ]


# ----------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_html_renders_snapshot_not_live_rules(booking: Booking) -> None:
    desc = _set_house_rules(booking.property, "Parties welcome.")
    desc.save()

    html = render_contract_html(booking)

    assert "Booking contract" in html
    assert booking.reference in html
    assert "House rules" in html
    assert "No parties." in html
    assert "Parties welcome." not in html
    assert "Terms and conditions" in html
    assert "<strong>T&amp;Cs</strong>" in html


@pytest.mark.django_db
def test_html_omits_house_rules_section_when_snapshot_blank(booking: Booking) -> None:
    booking.house_rules_snapshot = ""
    booking.save(update_fields=["house_rules_snapshot"])

    html = render_contract_html(booking)

    assert "House rules" not in html


@pytest.mark.django_db
def test_html_escapes_markup_in_snapshot(booking: Booking) -> None:
    booking.house_rules_snapshot = "Be nice <script>alert(1)</script>"
    booking.save(update_fields=["house_rules_snapshot"])

    html = render_contract_html(booking)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.django_db
def test_html_keeps_plain_text_house_rules_unstructured(booking: Booking) -> None:
    """Owner free-text is not Markdown: `# 1` and `* x` must survive verbatim."""
    booking.house_rules_snapshot = "# 1 No parties\n* No smoking\n  Indented note"
    booking.save(update_fields=["house_rules_snapshot"])

    html = render_contract_html(booking)

    assert "# 1 No parties" in html
    assert "* No smoking" in html
    assert "<h1" not in html
    assert "<li>" not in html
    assert "<pre>" not in html


@pytest.mark.django_db
def test_html_marks_settled_schedule_rows_as_paid(booking: Booking) -> None:
    booking.payments.all().delete()
    Payment.objects.create(
        booking=booking,
        purpose="deposit",
        status="succeeded",
        amount=Decimal("420.00"),
        currency=booking.currency,
    )

    html = render_contract_html(booking)

    assert ">Paid</td>" in html
    assert ">Due</td>" not in html


@pytest.mark.django_db
def test_html_omits_payment_schedule_when_no_rows(booking: Booking) -> None:
    booking.payments.all().delete()

    html = render_contract_html(booking)

    assert "Payment schedule" not in html


@pytest.mark.django_db
def test_html_includes_payment_schedule_rows(booking: Booking) -> None:
    booking.payments.all().delete()
    Payment.objects.create(
        booking=booking,
        purpose="deposit",
        status="pending",
        amount=Decimal("420.00"),
        currency=booking.currency,
        due_at=datetime(2026, 3, 1, 12, tzinfo=UTC),
    )

    html = render_contract_html(booking)

    assert "Payment schedule" in html
    assert "Deposit" in html
    assert "420.00" in html
    assert "1 March 2026" in html


# ----------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_render_contract_pdf_returns_pdf_bytes(booking: Booking) -> None:
    pdf = render_contract_pdf(booking)

    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")


# ----------------------------------------------------------------------
# API — GET /bookings/{id}/documents:preview
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_documents_preview_returns_contract_html(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/bookings/{booking.pk}/documents:preview")

    assert response.status_code == 200
    assert set(response.data) == {"html"}
    assert "No parties." in response.data["html"]
    assert booking.reference in response.data["html"]


@pytest.mark.django_db
def test_documents_preview_accepts_explicit_contract_kind(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/bookings/{booking.pk}/documents:preview?kind=contract")

    assert response.status_code == 200
    assert "No parties." in response.data["html"]


@pytest.mark.django_db
def test_documents_preview_rejects_unknown_kind(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/bookings/{booking.pk}/documents:preview?kind=voucher")

    assert response.status_code == 400
    assert response.data["code"] == "unsupported_kind"
    assert "voucher" in response.data["detail"]


@pytest.mark.django_db
def test_documents_preview_requires_authentication(api_client: APIClient, booking: Booking) -> None:
    response = api_client.get(f"/api/v1/bookings/{booking.pk}/documents:preview")

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_documents_preview_rejects_non_staff_user(api_client: APIClient, booking: Booking) -> None:
    """A logged-in customer account carries no staff role -> 403, not 200."""
    api_client.force_login(
        User.objects.create_user(email="guest@example.com", password="x", is_staff=False)
    )

    response = api_client.get(f"/api/v1/bookings/{booking.pk}/documents:preview")

    assert response.status_code == 403


@pytest.mark.django_db
def test_documents_preview_allows_viewer_role(api_client: APIClient, booking: Booking) -> None:
    """`IsReservationsWriter` reads for any staff role — the preview is a GET."""
    api_client.force_login(
        User.objects.create_user(
            email="viewer@example.com", password="x", is_staff=True, role=StaffRole.VIEWER
        )
    )

    response = api_client.get(f"/api/v1/bookings/{booking.pk}/documents:preview")

    assert response.status_code == 200


@pytest.mark.django_db
def test_documents_preview_declares_its_reads(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """The action's queryset branch must cover every FK the render walks."""
    api_client.force_login(staff)

    with assert_max_queries(5):
        response = api_client.get(f"/api/v1/bookings/{booking.pk}/documents:preview")

    assert response.status_code == 200


@pytest.mark.django_db
def test_documents_preview_404_for_archived_booking(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """Archive semantics match the other booking actions (`get_object`).

    Plan decision 10 exempts the *stored-document* endpoints (Unit 7) from the
    `is_archived` filter; the preview renders live off the booking through
    `BookingViewSet.get_object()`, so it inherits the viewset's filter.
    """
    api_client.force_login(staff)
    booking.is_archived = True
    booking.save(update_fields=["is_archived"])

    response = api_client.get(f"/api/v1/bookings/{booking.pk}/documents:preview")

    assert response.status_code == 404
