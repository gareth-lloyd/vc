"""API tests for /guests CRUD + :merge + :anonymize + nested history."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from core.tests import assert_max_queries
from pricing.models import Currency
from properties.models import Property
from reservations.enums import (
    GuestStatus,
    PaymentMethod,
    QuotationStatus,
)
from reservations.models import (
    Booking,
    Enquiry,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)


def _quote(
    *,
    enquiry: Enquiry,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    status: str = QuotationStatus.DRAFT.value,
    legacy_id: str | None = None,
) -> Quotation:
    return Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
        status=status,
        legacy_id=legacy_id,
    )


def _booking_for(
    *,
    quotation: Quotation,
    guest: Guest,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
    is_archived: bool = False,
) -> Booking:
    """Materialise the conversion chain: select a line on the quotation and
    create a Booking off it."""
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        children=0,
        total=Decimal("1400.00"),
        is_selected=True,
    )
    return Booking.objects.create(
        quotation_line=line,
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
        is_archived=is_archived,
    )


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def admin(db: None) -> User:
    return User.objects.create_user(
        is_staff=True, email="admin@example.com", password="x", role=StaffRole.ADMIN
    )


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True, email="staff@example.com", password="x", role=StaffRole.RESERVATIONS
    )


@pytest.mark.django_db
def test_create_guest(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/guests",
        {
            "first_name": "Alan",
            "last_name": "Turing",
            "email": "alan@example.com",
        },
        format="json",
    )

    assert response.status_code == 201
    assert Guest.objects.filter(email="alan@example.com").exists()


@pytest.mark.django_db
def test_create_phone_only_guest(api_client: APIClient, staff: User) -> None:
    """A phone-only guest is a first-class valid row (no fabricated email)."""
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/guests",
        {"first_name": "Alan", "last_name": "Turing", "phone": "+44 7911 123456"},
        format="json",
    )

    assert response.status_code == 201
    guest = Guest.objects.get(last_name="Turing")
    assert guest.email is None
    assert guest.phone == "+447911123456"  # normalized to E.164 on save


@pytest.mark.django_db
def test_create_guest_with_no_channel_returns_400(api_client: APIClient, staff: User) -> None:
    """The contactability CHECK is surfaced as a clean 400, not a 500."""
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/guests",
        {"first_name": "Alan", "last_name": "Turing"},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_create_email_preference_without_email_returns_400(
    api_client: APIClient, staff: User
) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/guests",
        {
            "first_name": "Alan",
            "last_name": "Turing",
            "phone": "+44 7700 900000",
            "contact_method": "email",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "contact_method" in response.json()["field_errors"]


@pytest.mark.django_db
def test_list_guests(api_client: APIClient, staff: User, guest: Guest) -> None:
    api_client.force_login(staff)

    response = api_client.get("/api/v1/guests")

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["results"]}
    assert guest.pk in ids


@pytest.mark.django_db
def test_patch_guest(api_client: APIClient, staff: User, guest: Guest) -> None:
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/guests/{guest.pk}",
        {"phone": "+44 7700 900000"},
        format="json",
    )

    assert response.status_code == 200
    guest.refresh_from_db()
    assert guest.phone == "+44 7700 900000"


@pytest.mark.django_db
def test_merge_requires_admin(api_client: APIClient, staff: User, guest: Guest) -> None:
    target = Guest.objects.create(first_name="Target", last_name="Guest", email="t@x.com")
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/guests/{guest.pk}:merge",
        {"target_guest_id": target.pk},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_merge_hard_deletes_source(api_client: APIClient, admin: User, guest: Guest) -> None:
    target = Guest.objects.create(first_name="Target", last_name="Guest", email="t@x.com")
    api_client.force_login(admin)

    response = api_client.post(
        f"/api/v1/guests/{guest.pk}:merge",
        {"target_guest_id": target.pk},
        format="json",
    )

    assert response.status_code == 200
    assert not Guest.objects.filter(pk=guest.pk).exists()
    assert Guest.objects.filter(pk=target.pk).exists()


@pytest.mark.django_db
def test_merge_into_self_returns_400(api_client: APIClient, admin: User, guest: Guest) -> None:
    api_client.force_login(admin)

    response = api_client.post(
        f"/api/v1/guests/{guest.pk}:merge",
        {"target_guest_id": guest.pk},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_anonymize_redacts_pii(api_client: APIClient, admin: User, guest: Guest) -> None:
    api_client.force_login(admin)

    response = api_client.post(f"/api/v1/guests/{guest.pk}:anonymize")

    assert response.status_code == 200
    guest.refresh_from_db()
    assert guest.status == GuestStatus.ANONYMIZED.value
    assert guest.first_name == "[REDACTED]"


@pytest.mark.django_db
def test_anonymize_requires_admin(api_client: APIClient, staff: User, guest: Guest) -> None:
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/guests/{guest.pk}:anonymize")

    assert response.status_code == 403


# ----------------------------------------------------------------------
# Nested enquiry history — quote_count + converted_booking (M3-B1)
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_guest_enquiries_includes_quote_count_and_converted_booking(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """History rows carry the count of real quotations and the converted
    booking when an ACCEPTED quotation's selected line was booked."""
    enquiry = Enquiry.objects.create(guest=guest, first_name="Ada", last_name="L", adults=2)
    _quote(
        enquiry=enquiry, guest=guest, gbp=gbp, terms=terms, status=QuotationStatus.CANCELLED.value
    )
    accepted = _quote(
        enquiry=enquiry, guest=guest, gbp=gbp, terms=terms, status=QuotationStatus.ACCEPTED.value
    )
    booking = _booking_for(
        quotation=accepted, guest=guest, property_=property_, gbp=gbp, terms=terms
    )
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/guests/{guest.pk}/enquiries")

    assert response.status_code == 200
    row = next(r for r in response.json()["results"] if r["id"] == enquiry.pk)
    assert row["quote_count"] == 2
    assert row["converted_booking"]["reference"] == booking.reference
    assert row["converted_booking"]["status"] == booking.status


@pytest.mark.django_db
def test_guest_enquiries_no_conversion_returns_null_booking(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    enquiry = Enquiry.objects.create(guest=guest, first_name="Ada", last_name="L", adults=2)
    _quote(enquiry=enquiry, guest=guest, gbp=gbp, terms=terms, status=QuotationStatus.SENT.value)
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/guests/{guest.pk}/enquiries")

    row = next(r for r in response.json()["results"] if r["id"] == enquiry.pk)
    assert row["quote_count"] == 1
    assert row["converted_booking"] is None


@pytest.mark.django_db
def test_guest_enquiries_excludes_legacy_synthetic_quotations(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """`booking-`-prefixed synthetic quotations (BookingLoader fill rows) must
    not inflate the quote count — they leak into no public API."""
    enquiry = Enquiry.objects.create(guest=guest, first_name="Ada", last_name="L", adults=2)
    _quote(enquiry=enquiry, guest=guest, gbp=gbp, terms=terms, status=QuotationStatus.SENT.value)
    _quote(
        enquiry=enquiry,
        guest=guest,
        gbp=gbp,
        terms=terms,
        status=QuotationStatus.DRAFT.value,
        legacy_id="booking-9999",
    )
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/guests/{guest.pk}/enquiries")

    row = next(r for r in response.json()["results"] if r["id"] == enquiry.pk)
    assert row["quote_count"] == 1


@pytest.mark.django_db
def test_guest_quotations_excludes_legacy_synthetic_quotations(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """`GET /guests/{id}/quotations` is a Quotation-surfacing read, so it must
    route through `.real()` like every other one — the BookingLoader's
    `booking-` synthetic fill rows are an internal artefact and must never reach
    the operator's guest-quotations list."""
    enquiry = Enquiry.objects.create(guest=guest, first_name="Ada", last_name="L", adults=2)
    real = _quote(enquiry=enquiry, guest=guest, gbp=gbp, terms=terms)
    _quote(enquiry=enquiry, guest=guest, gbp=gbp, terms=terms, legacy_id="booking-9999")
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/guests/{guest.pk}/quotations")

    assert response.status_code == 200
    refs = {row["reference"] for row in response.json()["results"]}
    assert refs == {real.reference}


@pytest.mark.django_db
def test_guest_enquiries_converted_booking_skips_archived(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """An archived (cancelled/superseded) booking must not be surfaced as the
    conversion — converted_booking stays null."""
    enquiry = Enquiry.objects.create(guest=guest, first_name="Ada", last_name="L", adults=2)
    accepted = _quote(
        enquiry=enquiry, guest=guest, gbp=gbp, terms=terms, status=QuotationStatus.ACCEPTED.value
    )
    _booking_for(
        quotation=accepted,
        guest=guest,
        property_=property_,
        gbp=gbp,
        terms=terms,
        is_archived=True,
    )
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/guests/{guest.pk}/enquiries")

    row = next(r for r in response.json()["results"] if r["id"] == enquiry.pk)
    assert row["converted_booking"] is None


@pytest.mark.django_db
def test_guest_enquiries_query_count_bounded(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """The nested-history endpoint stays query-bounded regardless of how many
    enquiries/quotations/bookings hang off the guest (3-level prefetch)."""
    for _ in range(4):
        enquiry = Enquiry.objects.create(guest=guest, first_name="Ada", last_name="L", adults=2)
        accepted = _quote(
            enquiry=enquiry,
            guest=guest,
            gbp=gbp,
            terms=terms,
            status=QuotationStatus.ACCEPTED.value,
        )
        _booking_for(quotation=accepted, guest=guest, property_=property_, gbp=gbp, terms=terms)
    api_client.force_login(staff)

    with assert_max_queries(12):
        response = api_client.get(f"/api/v1/guests/{guest.pk}/enquiries")
    assert response.status_code == 200
