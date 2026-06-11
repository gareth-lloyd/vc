"""API tests for `GET /availability` — the multi-villa timeline read.

The response carries two band arrays: `records` (live operator holds, the
pre-existing shape `fetchPropertyHolds` consumes) and `bookings` (occupying
bookings, which have no covering hold row).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from core.tests import assert_max_queries
from pricing.models import Currency
from properties.models import Property
from reservations.enums import BookingHoldReason, BookingStatus, PaymentMethod
from reservations.models import (
    Booking,
    BookingHold,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/availability"


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="avail-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


def _make_booking(
    *,
    property: Property,
    currency: Currency,
    guest: Guest,
    terms: TermsVersion,
    date_from: date,
    date_to: date,
    status: str = BookingStatus.AWAITING_DEPOSIT.value,
) -> Booking:
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        property=property,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        currency=currency,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        status=status,
    )


# Sentinel: "caller didn't pass expires_at" (None is a real value — never expires).
_DEFAULT_EXPIRY: Any = object()


def _hold(
    *,
    property: Property,
    date_from: date,
    date_to: date,
    reason: str = BookingHoldReason.OWNER_BLOCK.value,
    expires_at: datetime | None = _DEFAULT_EXPIRY,
    booking: Booking | None = None,
) -> BookingHold:
    if expires_at is _DEFAULT_EXPIRY:
        expires_at = timezone.now() + timedelta(days=30)
    return BookingHold.objects.create(
        property=property,
        booking=booking,
        date_from=date_from,
        date_to=date_to,
        expires_at=expires_at,
        reason=reason,
    )


def _get(client: APIClient, property_ids: str, **params: str) -> Any:
    return client.get(
        URL,
        {"property_ids": property_ids, "from": "2026-06-01", "to": "2026-07-06", **params},
    )


# ----------------------------------------------------------------------
# Validation + auth
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "params",
    [
        {},
        {"property_ids": "1"},
        {"property_ids": "1", "from": "2026-06-01"},
        {"from": "2026-06-01", "to": "2026-07-06"},
    ],
)
def test_missing_params_return_400(
    api_client: APIClient, staff: User, params: dict[str, str]
) -> None:
    api_client.force_login(staff)
    resp = api_client.get(URL, params)
    assert resp.status_code == 400
    assert resp.json()["code"] == "validation_error"


def test_anonymous_is_rejected(api_client: APIClient) -> None:
    resp = _get(api_client, "1")
    assert resp.status_code == 403


def test_non_staff_is_rejected(api_client: APIClient) -> None:
    user = User.objects.create_user(is_staff=False, email="avail-portal@example.com", password="x")
    api_client.force_login(user)
    resp = _get(api_client, "1")
    assert resp.status_code == 403


def test_non_ascii_digits_are_rejected_not_500(api_client: APIClient, staff: User) -> None:
    # "²" passes str.isdigit() but int() raises ValueError — must 400, not 500.
    api_client.force_login(staff)
    resp = _get(api_client, "²")
    assert resp.status_code == 400
    assert resp.json()["code"] == "validation_error"


def test_more_than_50_property_ids_returns_400(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    ids = ",".join(str(n) for n in range(1, 52))
    resp = _get(api_client, ids)
    assert resp.status_code == 400
    assert resp.json()["code"] == "validation_error"


# ----------------------------------------------------------------------
# Response shape
# ----------------------------------------------------------------------
def test_records_keep_existing_hold_shape(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    hold = _hold(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        reason=BookingHoldReason.MAINTENANCE.value,
    )
    api_client.force_login(staff)
    resp = _get(api_client, str(property_.pk))
    assert resp.status_code == 200
    body = resp.json()
    assert body["bookings"] == []
    (record,) = body["records"]
    assert record["id"] == hold.pk
    assert record["property"] == property_.pk
    assert record["date_from"] == "2026-06-10"
    assert record["date_to"] == "2026-06-17"
    assert record["reason"] == BookingHoldReason.MAINTENANCE.value
    assert set(record) == {
        "id",
        "property",
        "date_from",
        "date_to",
        "expires_at",
        "released_at",
        "reason",
        "notes",
        "created_at",
    }


def test_bookings_carry_timeline_fields(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    guest: Guest,
    terms: TermsVersion,
) -> None:
    booking = _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    api_client.force_login(staff)
    resp = _get(api_client, str(property_.pk))
    assert resp.status_code == 200
    (band,) = resp.json()["bookings"]
    assert band == {
        "id": booking.pk,
        "property": property_.pk,
        "date_from": "2026-06-10",
        "date_to": "2026-06-17",
        "status": BookingStatus.AWAITING_DEPOSIT.value,
        "reference": booking.reference,
        "guest_name": "Ada Lovelace",
    }


# ----------------------------------------------------------------------
# Band selection rules
# ----------------------------------------------------------------------
def test_expired_unreleased_hold_is_excluded_null_expiry_included(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    _hold(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() - timedelta(days=1),
    )
    forever = _hold(
        property=property_,
        date_from=date(2026, 6, 20),
        date_to=date(2026, 6, 27),
        expires_at=None,
    )
    api_client.force_login(staff)
    resp = _get(api_client, str(property_.pk))
    assert [r["id"] for r in resp.json()["records"]] == [forever.pk]


def test_booking_linked_hold_excluded_booking_present(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    guest: Guest,
    terms: TermsVersion,
) -> None:
    booking = _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    _hold(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        reason=BookingHoldReason.QUOTATION_OPEN.value,
        booking=booking,
    )
    api_client.force_login(staff)
    resp = _get(api_client, str(property_.pk))
    body = resp.json()
    assert body["records"] == []
    assert [b["id"] for b in body["bookings"]] == [booking.pk]


# ----------------------------------------------------------------------
# Query bound
# ----------------------------------------------------------------------
def test_query_count_is_constant(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    guest: Guest,
    terms: TermsVersion,
) -> None:
    others = [
        Property.objects.create(
            name=f"Villa {n}",
            display_name=f"Villa {n}",
            slug=f"villa-{n}",
            category=property_.category,
            group=property_.group,
            region=property_.region,
        )
        for n in range(2)
    ]
    for n, prop in enumerate([property_, *others]):
        _hold(
            property=prop,
            date_from=date(2026, 6, 1 + n),
            date_to=date(2026, 6, 8 + n),
        )
        _make_booking(
            property=prop,
            currency=gbp,
            guest=guest,
            terms=terms,
            date_from=date(2026, 6, 14 + n),
            date_to=date(2026, 6, 21 + n),
        )
    api_client.force_login(staff)
    ids = ",".join(str(p.pk) for p in [property_, *others])
    with assert_max_queries(8):
        resp = _get(api_client, ids)
    body = resp.json()
    assert len(body["records"]) == 3
    assert len(body["bookings"]) == 3
