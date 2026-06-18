"""API tests for nested /bookings/{id}/concierge-items."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from pricing.models import Currency
from properties.models import Property
from reservations.enums import ConciergeStatus, PaymentMethod
from reservations.models import (
    Booking,
    BookingConciergeItem,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)
from reservations.services.person_sync import person_for_guest


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="conc-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def booking(
    db: None,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
    person = person_for_guest(guest)
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        person=person,
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
    )


@pytest.mark.django_db
def test_concierge_crud(
    api_client: APIClient, staff: User, booking: Booking, gbp: Currency
) -> None:
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/concierge-items",
        {
            "tier": "quintessential",
            "name": "Chef night",
            "quantity": 1,
            "unit": "event",
            "unit_price": "350.00",
            "currency": gbp.pk,
        },
        format="json",
    )
    assert create.status_code == 201, create.data
    item_id = BookingConciergeItem.objects.get().pk
    # Writes must respond with the read representation (id, status, timestamps) —
    # the FE parses the response directly, and the write serializer's echo
    # lacks the fields its schema requires.
    assert create.data["id"] == item_id
    assert create.data["status"] == ConciergeStatus.REQUESTED.value

    listing = api_client.get(f"/api/v1/bookings/{booking.pk}/concierge-items")
    assert listing.data["count"] == 1

    patch = api_client.patch(
        f"/api/v1/bookings/{booking.pk}/concierge-items/{item_id}",
        {"quantity": 2},
        format="json",
    )
    assert patch.status_code == 200
    assert patch.data["id"] == item_id
    assert patch.data["status"] == ConciergeStatus.REQUESTED.value
    assert patch.data["quantity"] == 2

    delete = api_client.delete(
        f"/api/v1/bookings/{booking.pk}/concierge-items/{item_id}",
    )
    assert delete.status_code == 204


@pytest.mark.django_db
def test_concierge_confirm_action(
    api_client: APIClient, staff: User, booking: Booking, gbp: Currency
) -> None:
    item = BookingConciergeItem.objects.create(
        booking=booking,
        name="Yacht charter",
        unit_price=Decimal("2500.00"),
        currency=gbp,
    )
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/concierge-items/{item.pk}:confirm",
    )
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.status == ConciergeStatus.CONFIRMED.value


@pytest.mark.django_db
def test_concierge_reorder(
    api_client: APIClient, staff: User, booking: Booking, gbp: Currency
) -> None:
    a = BookingConciergeItem.objects.create(
        booking=booking, name="A", unit_price=Decimal("10"), currency=gbp
    )
    b = BookingConciergeItem.objects.create(
        booking=booking, name="B", unit_price=Decimal("20"), currency=gbp
    )
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/concierge-items:reorder",
        {"ids": [b.pk, a.pk]},
        format="json",
    )
    assert response.status_code == 200
    assert {row["id"] for row in response.data} == {a.pk, b.pk}
