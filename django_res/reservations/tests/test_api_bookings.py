"""API tests for /bookings — list/detail/patch + state-machine action set."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.enums import StaffRole
from accounts.models import User
from pricing.models import Currency, RateRule
from properties.models import Property
from reservations.enums import BookingStatus, PaymentMethod
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
        email="book-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        email="book-viewer@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


@pytest.fixture
def booking(
    db: None,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> Booking:
    quotation = Quotation.objects.create(
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
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        property=property_,
        date_from=line.date_from,
        date_to=line.date_to,
        adults=line.adults,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )


@pytest.mark.django_db
def test_list_bookings(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)
    response = api_client.get("/api/v1/bookings")

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["reference"] == booking.reference


@pytest.mark.django_db
def test_list_bookings__hides_archived_by_default(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    booking.cancel("test")
    booking.archive()
    api_client.force_login(staff)

    response = api_client.get("/api/v1/bookings")
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_archived_listing_returns_archived_bookings(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    booking.cancel("test")
    booking.archive()
    api_client.force_login(staff)

    response = api_client.get("/api/v1/bookings/archived")
    assert response.status_code == 200
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_detail_booking(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")
    assert response.status_code == 200
    assert response.data["reference"] == booking.reference
    assert "pricing_snapshot" in response.data


@pytest.mark.django_db
def test_patch_booking__updates_non_state_fields(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/bookings/{booking.pk}",
        {"site_source": "agent_portal"},
        format="json",
    )
    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.site_source == "agent_portal"


@pytest.mark.django_db
def test_cancel_booking(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}:cancel",
        {"reason": "guest changed plans"},
        format="json",
    )
    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CANCELLED.value


@pytest.mark.django_db
def test_owner_decline(api_client: APIClient, staff: User, booking: Booking) -> None:
    booking.status = BookingStatus.PENDING_OWNER_APPROVAL.value
    booking.save(update_fields=["status"])
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}:owner-decline",
        {"reason": "calendar conflict"},
        format="json",
    )

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.DECLINED.value


@pytest.mark.django_db
def test_owner_approve(api_client: APIClient, staff: User, booking: Booking) -> None:
    booking.status = BookingStatus.PENDING_OWNER_APPROVAL.value
    booking.save(update_fields=["status"])
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/bookings/{booking.pk}:owner-approve")

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.status == BookingStatus.AWAITING_DEPOSIT.value


@pytest.mark.django_db
def test_modify_guests_recomputes_pricing(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}:modify-guests",
        {"adults": 4, "children": 1, "reason": "extended family"},
        format="json",
    )
    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.adults == 4
    assert booking.children == 1


@pytest.mark.django_db
def test_archive_blocked_on_active_booking(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/bookings/{booking.pk}:archive")

    # AWAITING_DEPOSIT is not terminal — archive raises InvalidTransition → 409.
    assert response.status_code == 409


@pytest.mark.django_db
def test_archive_then_restore_round_trip(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    booking.cancel("test")
    api_client.force_login(staff)

    archive = api_client.post(f"/api/v1/bookings/{booking.pk}:archive")
    assert archive.status_code == 200

    booking.refresh_from_db()
    assert booking.is_archived is True

    restore = api_client.post(f"/api/v1/bookings/{booking.pk}:restore")
    assert restore.status_code == 200

    booking.refresh_from_db()
    assert booking.is_archived is False


@pytest.mark.django_db
def test_activity_returns_event_timeline(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    booking.cancel("test")
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/bookings/{booking.pk}/activity")
    assert response.status_code == 200
    assert any(row["to_status"] == BookingStatus.CANCELLED.value for row in response.data)


@pytest.mark.django_db
def test_viewer_cannot_cancel_booking(
    api_client: APIClient, viewer: User, booking: Booking
) -> None:
    api_client.force_login(viewer)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}:cancel",
        {"reason": "viewer attempt"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_bookings_have_no_delete(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)
    response = api_client.delete(f"/api/v1/bookings/{booking.pk}")
    assert response.status_code == 405


@pytest.mark.django_db
def test_notes_crud(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/notes",
        {"body": "guest gluten-free", "kind": "concierge"},
        format="json",
    )
    assert create.status_code == 201

    note_id = create.data["id"]

    listing = api_client.get(f"/api/v1/bookings/{booking.pk}/notes")
    assert listing.data["count"] == 1

    patch = api_client.patch(
        f"/api/v1/bookings/{booking.pk}/notes/{note_id}",
        {"is_pinned": True},
        format="json",
    )
    assert patch.status_code == 200
