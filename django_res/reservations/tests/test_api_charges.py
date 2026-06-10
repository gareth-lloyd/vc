"""API tests for nested /bookings/{id}/charge-items."""

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
from reservations.enums import BookingStatus, PaymentMethod
from reservations.models import (
    Booking,
    BookingChargeItem,
    BookingEvent,
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
        is_staff=True,
        email="charge-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="charge-viewer@example.com",
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
) -> Booking:
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
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


def _set_status(booking: Booking, status: BookingStatus) -> None:
    updates: dict[str, object] = {"status": status.value}
    if status is BookingStatus.CANCELLED:
        # `booking_cancelled_status_requires_cancelled_at` check constraint.
        updates["cancelled_at"] = timezone.now()
    Booking.objects.filter(pk=booking.pk).update(**updates)


@pytest.mark.django_db
def test_charge_crud(api_client: APIClient, staff: User, booking: Booking) -> None:
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/charge-items",
        {"label": "Late checkout", "amount": "150.00", "notes": "Agreed by phone"},
        format="json",
    )
    assert create.status_code == 201, create.data
    item = BookingChargeItem.objects.get()
    assert item.amount == Decimal("150.00")
    assert item.currency == booking.currency
    # Writes respond with the read representation, so the FE can use the row.
    assert create.data["id"] == item.pk
    assert create.data["currency_code"] == "GBP"

    listing = api_client.get(f"/api/v1/bookings/{booking.pk}/charge-items")
    assert listing.data["count"] == 1
    assert listing.data["results"][0]["label"] == "Late checkout"

    patch = api_client.patch(
        f"/api/v1/bookings/{booking.pk}/charge-items/{item.pk}",
        {"amount": "-75.00"},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    assert patch.data["id"] == item.pk
    assert patch.data["amount"] == "-75.00"
    item.refresh_from_db()
    assert item.amount == Decimal("-75.00")

    delete = api_client.delete(f"/api/v1/bookings/{booking.pk}/charge-items/{item.pk}")
    assert delete.status_code == 204
    assert not BookingChargeItem.objects.exists()


@pytest.mark.django_db
def test_viewer_can_read_but_not_write(
    api_client: APIClient, staff: User, viewer: User, booking: Booking, gbp: Currency
) -> None:
    BookingChargeItem.objects.create(
        booking=booking, label="Heli", amount=Decimal("900.00"), currency=gbp
    )

    api_client.force_login(viewer)
    listing = api_client.get(f"/api/v1/bookings/{booking.pk}/charge-items")
    assert listing.status_code == 200

    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/charge-items",
        {"label": "Nope", "amount": "10.00"},
        format="json",
    )
    assert create.status_code == 403


@pytest.mark.parametrize(
    "status",
    [BookingStatus.DRAFT, BookingStatus.PENDING_OWNER_APPROVAL, BookingStatus.CANCELLED],
)
@pytest.mark.django_db
def test_writes_refused_outside_active_states(
    api_client: APIClient, staff: User, booking: Booking, status: BookingStatus
) -> None:
    """Pre-approval negotiation belongs on the quotation; terminal bookings
    are closed books. Both refuse with 409."""
    _set_status(booking, status)
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/charge-items",
        {"label": "Late checkout", "amount": "150.00"},
        format="json",
    )
    assert create.status_code == 409, create.data


@pytest.mark.django_db
def test_update_and_delete_also_state_gated(
    api_client: APIClient, staff: User, booking: Booking, gbp: Currency
) -> None:
    item = BookingChargeItem.objects.create(
        booking=booking, label="Heli", amount=Decimal("900.00"), currency=gbp
    )
    _set_status(booking, BookingStatus.CANCELLED)
    api_client.force_login(staff)

    patch = api_client.patch(
        f"/api/v1/bookings/{booking.pk}/charge-items/{item.pk}",
        {"amount": "100.00"},
        format="json",
    )
    assert patch.status_code == 409

    delete = api_client.delete(f"/api/v1/bookings/{booking.pk}/charge-items/{item.pk}")
    assert delete.status_code == 409


@pytest.mark.django_db
def test_checked_in_booking_accepts_charges(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """Mid-stay extras are a core use case — CHECKED_IN stays writable."""
    _set_status(booking, BookingStatus.CHECKED_IN)
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/charge-items",
        {"label": "Chef night", "amount": "350.00"},
        format="json",
    )
    assert create.status_code == 201, create.data


@pytest.mark.django_db
def test_currency_defaults_to_booking_and_mismatch_is_rejected(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    api_client.force_login(staff)

    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/charge-items",
        {"label": "Late checkout", "amount": "150.00"},
        format="json",
    )
    assert create.status_code == 201
    assert BookingChargeItem.objects.get().currency == booking.currency

    mismatch = api_client.post(
        f"/api/v1/bookings/{booking.pk}/charge-items",
        {"label": "Wrong money", "amount": "150.00", "currency": eur.pk},
        format="json",
    )
    assert mismatch.status_code == 400
    assert "currency" in mismatch.data["field_errors"]


@pytest.mark.django_db
def test_zero_amount_rejected_as_field_error(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)
    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/charge-items",
        {"label": "Nothing", "amount": "0.00"},
        format="json",
    )
    assert create.status_code == 400
    assert "amount" in create.data["field_errors"]


@pytest.mark.django_db
def test_credit_below_negative_total_rejected(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """A credit may zero the booking out but never push the total negative."""
    api_client.force_login(staff)
    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/charge-items",
        {"label": "Too generous", "amount": "-1500.00"},
        format="json",
    )
    assert create.status_code == 400
    assert "amount" in create.data["field_errors"]


@pytest.mark.django_db
def test_mutations_write_booking_events(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)

    api_client.post(
        f"/api/v1/bookings/{booking.pk}/charge-items",
        {"label": "Late checkout", "amount": "150.00"},
        format="json",
    )
    item = BookingChargeItem.objects.get()
    api_client.patch(
        f"/api/v1/bookings/{booking.pk}/charge-items/{item.pk}",
        {"amount": "175.00"},
        format="json",
    )
    api_client.delete(f"/api/v1/bookings/{booking.pk}/charge-items/{item.pk}")

    events = list(
        BookingEvent.objects.filter(booking=booking, reason__startswith="charge_item_").order_by(
            "created_at"
        )
    )
    assert [e.reason for e in events] == [
        "charge_item_created",
        "charge_item_updated",
        "charge_item_deleted",
    ]
    created, updated, deleted = events
    assert created.actor == staff
    assert created.meta["after"]["amount"] == "150.00"
    assert created.meta["before"] is None
    assert created.meta["charges_total"] == "150.00"
    assert updated.meta["before"]["amount"] == "150.00"
    assert updated.meta["after"]["amount"] == "175.00"
    assert deleted.meta["after"] is None
    assert deleted.meta["charges_total"] == "0.00"


@pytest.mark.django_db
def test_post_charge_resizes_pending_schedule_end_to_end(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """The full chain: API write → service → signal → payments resync."""
    from payments.enums import PaymentPurpose
    from payments.models import Payment
    from payments.services import PaymentScheduler
    from properties.models.finance import GroupFinance, PropertyFinance

    GroupFinance.objects.get_or_create(group=booking.property.group)
    PropertyFinance.objects.get_or_create(property=booking.property)
    fresh = Booking.objects.get(pk=booking.pk)
    PaymentScheduler.create_for_booking(fresh)

    api_client.force_login(staff)
    create = api_client.post(
        f"/api/v1/bookings/{booking.pk}/charge-items",
        {"label": "Late checkout", "amount": "200.00"},
        format="json",
    )
    assert create.status_code == 201, create.data

    deposit = Payment.objects.get(booking=booking, purpose=PaymentPurpose.DEPOSIT.value)
    balance = Payment.objects.get(booking=booking, purpose=PaymentPurpose.BALANCE.value)
    assert deposit.amount == Decimal("480.00")
    assert balance.amount == Decimal("1120.00")


@pytest.mark.django_db
def test_list_query_count_bound(
    api_client: APIClient, staff: User, booking: Booking, gbp: Currency
) -> None:
    for i in range(5):
        BookingChargeItem.objects.create(
            booking=booking, label=f"Charge {i}", amount=Decimal("10.00"), currency=gbp
        )
    api_client.force_login(staff)
    with assert_max_queries(6):
        response = api_client.get(f"/api/v1/bookings/{booking.pk}/charge-items")
    assert response.data["count"] == 5
