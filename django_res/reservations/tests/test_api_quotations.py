"""API tests for /quotations CRUD + line CRUD + :send + :convert."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.enums import StaffRole
from accounts.models import User
from pricing.models import Currency
from properties.enums import PrefilledChangeOverDay
from properties.models import Property
from properties.models.settings import PropertySettings
from reservations.enums import QuotationStatus
from reservations.models import (
    Booking,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        email="quo-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def quotation(
    db: None,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> Quotation:
    return Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )


@pytest.fixture
def line(quotation: Quotation, property_: Property) -> QuotationLine:
    return QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )


@pytest.mark.django_db
def test_list_quotations(api_client: APIClient, staff: User, quotation: Quotation) -> None:
    api_client.force_login(staff)
    response = api_client.get("/api/v1/quotations")

    assert response.status_code == 200
    assert response.data["count"] == 1
    row = response.data["results"][0]
    # Surface human-readable values alongside the FK ids so the FE doesn't
    # display opaque #ids (regression: STAY-style "Guest #64" / "Enquiry #66").
    assert row["guest_name"] == "Ada Lovelace"
    assert row["enquiry_reference"] is None
    assert row["agent_name"] is None


@pytest.mark.django_db
def test_retrieve_quotation_exposes_readable_names(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/quotations/{quotation.pk}")

    assert response.status_code == 200
    assert response.data["guest_name"] == "Ada Lovelace"
    expected_property_name = line.property.display_name or line.property.name
    assert response.data["lines"][0]["property_name"] == expected_property_name


@pytest.mark.django_db
def test_create_quotation(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/quotations",
        {
            "guest": guest.pk,
            "currency": gbp.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert Quotation.objects.count() == 1


@pytest.mark.django_db
def test_retrieve_quotation_includes_lines(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/quotations/{quotation.pk}")

    assert response.status_code == 200
    assert len(response.data["lines"]) == 1
    assert response.data["lines"][0]["id"] == line.pk


@pytest.mark.django_db
def test_send_quotation(api_client: APIClient, staff: User, quotation: Quotation) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/quotations/{quotation.pk}:send")

    assert response.status_code == 200
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.SENT.value


@pytest.mark.django_db
def test_duplicate_quotation_clones_lines(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/quotations/{quotation.pk}:duplicate")

    assert response.status_code == 201
    clone_id = response.data["id"]
    assert clone_id != quotation.pk
    assert QuotationLine.objects.filter(quotation_id=clone_id).count() == 1


@pytest.mark.django_db
def test_lines_crud(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    property_: Property,
) -> None:
    api_client.force_login(staff)

    # Create
    create = api_client.post(
        f"/api/v1/quotations/{quotation.pk}/lines",
        {
            "property": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
            "children": 0,
        },
        format="json",
    )
    assert create.status_code == 201

    line_pk = QuotationLine.objects.get().pk

    # List
    listing = api_client.get(f"/api/v1/quotations/{quotation.pk}/lines")
    assert listing.status_code == 200
    assert listing.data["count"] == 1

    # Patch
    patch = api_client.patch(
        f"/api/v1/quotations/{quotation.pk}/lines/{line_pk}",
        {"adults": 3},
        format="json",
    )
    assert patch.status_code == 200

    # Delete
    delete = api_client.delete(f"/api/v1/quotations/{quotation.pk}/lines/{line_pk}")
    assert delete.status_code == 204


@pytest.mark.django_db
def test_convert_creates_booking(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    quotation.send()
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_quotation_convert_endpoint_attributes_to_request_user(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """The auto-conversion `EnquiryEvent.actor` must be the request user.

    Bug #5: `QuotationViewSet.convert` called `quotation.accept(line)`
    without `actor=`, so the resulting CONVERTED event was attributed to
    `None` instead of the logged-in operator — the audit trail lost the
    actor for every quote-to-booking conversion via the API.
    """
    from reservations.enums import EnquiryEventKind
    from reservations.models import Enquiry, EnquiryEvent

    enquiry = Enquiry.objects.create(
        guest=guest, email=guest.email, first_name="Ada", last_name="Lovelace"
    )
    quotation = Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
    quotation.send()
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk},
        format="json",
    )
    assert response.status_code == 201, response.data

    converted_event = EnquiryEvent.objects.get(
        enquiry=enquiry,
        kind=EnquiryEventKind.CONVERTED.value,
    )
    assert converted_event.actor_id == staff.pk


@pytest.mark.django_db
def test_convert_enforces_changeover_with_override_escape(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    PropertySettings.objects.create(
        property=line.property,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    quotation.send()
    api_client.force_login(staff)

    # 2026-06-10 (line fixture) is a Wednesday — wrong changeover day.
    rejected = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk},
        format="json",
    )
    assert rejected.status_code == 422, rejected.data
    assert rejected.data["code"] == "changeover_violation"
    assert Booking.objects.count() == 0

    accepted = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk, "allow_changeover_override": True},
        format="json",
    )
    assert accepted.status_code == 201, accepted.data
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_convert_overlap_rolls_back_quotation_acceptance(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    line: QuotationLine,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """If the booking service raises OverlappingBooking, the quotation must NOT
    be left ACCEPTED — the whole convert is one transaction."""
    from reservations.enums import BookingStatus, PaymentMethod
    from reservations.models import Booking as BookingModel

    # Pre-existing AWAITING_DEPOSIT booking holds 2026-06-10..06-17 on the
    # same property, so converting the overlapping quotation must fail.
    other_quotation = Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    other_line = QuotationLine.objects.create(
        quotation=other_quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
    existing = BookingModel.objects.create(
        quotation_line=other_line,
        guest=guest,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )
    assert existing.status == BookingStatus.AWAITING_DEPOSIT.value

    quotation.send()
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:convert",
        {"line": line.pk},
        format="json",
    )

    # Domain error → 409 from canonical_exception_handler.
    assert response.status_code == 409, response.data
    assert response.data["code"] == "overlapping_booking"

    # Quotation must NOT have been left ACCEPTED.
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.SENT.value
    # No second booking created.
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_withdraw_quotation(api_client: APIClient, staff: User, quotation: Quotation) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/quotations/{quotation.pk}:withdraw",
        {"reason": "guest cancelled"},
        format="json",
    )

    assert response.status_code == 200
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.CANCELLED.value


@pytest.mark.django_db
def test_pdf_returns_501(api_client: APIClient, staff: User, quotation: Quotation) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/quotations/{quotation.pk}/pdf")
    assert response.status_code == 501
