"""API tests for the concierge coverage matrix.

- ``GET  /api/v1/concierge/overview``
- ``POST /api/v1/concierge/{booking_id}/coverage/{service}:set-status``
"""

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
    BookingStatus,
    ConciergeService,
    ConciergeTier,
    PaymentMethod,
    ServiceStatus,
)
from reservations.models import (
    Booking,
    BookingConciergeItem,
    BookingServiceCoverage,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)

pytestmark = pytest.mark.django_db

OVERVIEW_URL = "/api/v1/concierge/overview"


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="concierge-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        is_staff=True, email="concierge-viewer@example.com", password="x", role=StaffRole.VIEWER
    )


def _make_booking(
    *,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    days_from: int,
    days_to: int,
    status: str = BookingStatus.AWAITING_DEPOSIT.value,
) -> Booking:
    """Build a booking via direct create with today-relative dates.

    Callers pass non-overlapping windows so the no-overlap constraint on the
    shared property is never tripped.
    """
    from reservations.services.person_sync import person_for_guest

    date_from = date.today() + timedelta(days=days_from)
    date_to = date.today() + timedelta(days=days_to)
    person = person_for_guest(guest)
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(person=person),
        guest=guest,
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        person=person,
        property=property_,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
        status=status,
    )


@pytest.fixture
def live_booking(guest: Guest, gbp: Currency, terms: TermsVersion, property_: Property) -> Booking:
    return _make_booking(
        guest=guest, gbp=gbp, terms=terms, property_=property_, days_from=10, days_to=17
    )


def test_overview_lists_live_booking_with_service_defaults(
    api_client: APIClient, staff: User, live_booking: Booking
) -> None:
    api_client.force_login(staff)
    response = api_client.get(OVERVIEW_URL)

    assert response.status_code == 200
    assert len(response.data) == 1
    row = response.data[0]
    assert row["reference"] == live_booking.reference
    assert row["guest_name"] == "Ada Lovelace"
    assert row["property_name"] == "Test Villa"
    assert row["arrival_in_days"] == 10
    # Every service column present; untouched cells default to not_started.
    assert set(row["services"]) == set(ConciergeService.values)
    assert all(v == ServiceStatus.NOT_STARTED.value for v in row["services"].values())
    assert row["progress"] == 0
    assert row["tier"] is None


def test_overview_reflects_coverage_and_progress(
    api_client: APIClient, staff: User, live_booking: Booking
) -> None:
    BookingServiceCoverage.objects.create(
        booking=live_booking, service="chef", status=ServiceStatus.DONE.value
    )
    BookingServiceCoverage.objects.create(
        booking=live_booking, service="car", status=ServiceStatus.WORKING_ON_IT.value
    )
    # not_required drops out of the progress denominator.
    BookingServiceCoverage.objects.create(
        booking=live_booking, service="boat", status=ServiceStatus.NOT_REQUIRED.value
    )
    api_client.force_login(staff)
    row = api_client.get(OVERVIEW_URL).data[0]

    assert row["services"]["chef"] == ServiceStatus.DONE.value
    assert row["services"]["car"] == ServiceStatus.WORKING_ON_IT.value
    assert row["services"]["boat"] == ServiceStatus.NOT_REQUIRED.value
    assert row["services"]["spa"] == ServiceStatus.NOT_STARTED.value
    # Full-matrix denominator: 13 services minus boat (not_required) = 12
    # applicable; chef is the only one done → round(1/12*100) = 8.
    assert row["progress"] == 8


def test_overview_derives_tier_from_concierge_items(
    api_client: APIClient, staff: User, live_booking: Booking, gbp: Currency
) -> None:
    BookingConciergeItem.objects.create(
        booking=live_booking,
        name="Private chef",
        currency=gbp,
        tier=ConciergeTier.QUINTESSENTIAL.value,
    )
    BookingConciergeItem.objects.create(
        booking=live_booking, name="Yacht day", currency=gbp, tier=ConciergeTier.SIGNATURE.value
    )
    api_client.force_login(staff)
    row = api_client.get(OVERVIEW_URL).data[0]
    # Signature outranks Quintessential.
    assert row["tier"] == ConciergeTier.SIGNATURE.value


def test_overview_excludes_archived_terminal_and_departed(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    live_booking: Booking,
) -> None:
    # Departed: already checked out by date.
    _make_booking(
        guest=guest, gbp=gbp, terms=terms, property_=property_, days_from=-20, days_to=-10
    )
    # Terminal: cancelled.
    cancelled = _make_booking(
        guest=guest, gbp=gbp, terms=terms, property_=property_, days_from=30, days_to=37
    )
    cancelled.cancel("test")
    # Archived.
    archived = _make_booking(
        guest=guest, gbp=gbp, terms=terms, property_=property_, days_from=50, days_to=57
    )
    archived.cancel("test")
    archived.archive()

    api_client.force_login(staff)
    response = api_client.get(OVERVIEW_URL)
    assert len(response.data) == 1
    assert response.data[0]["reference"] == live_booking.reference


def test_overview_query_count_is_constant(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    for offset in (10, 30, 50):
        booking = _make_booking(
            guest=guest,
            gbp=gbp,
            terms=terms,
            property_=property_,
            days_from=offset,
            days_to=offset + 5,
        )
        BookingServiceCoverage.objects.create(
            booking=booking, service="chef", status=ServiceStatus.DONE.value
        )
        BookingConciergeItem.objects.create(
            booking=booking, name="Chef", currency=gbp, tier=ConciergeTier.SIGNATURE.value
        )
    api_client.force_login(staff)
    with assert_max_queries(8):
        response = api_client.get(OVERVIEW_URL)
    assert len(response.data) == 3


def test_overview_requires_authentication(api_client: APIClient, live_booking: Booking) -> None:
    response = api_client.get(OVERVIEW_URL)
    assert response.status_code in (401, 403)


def _set_status_url(booking_id: int, service: str) -> str:
    return f"/api/v1/concierge/{booking_id}/coverage/{service}:set-status"


def test_set_status_happy_path(api_client: APIClient, staff: User, live_booking: Booking) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        _set_status_url(live_booking.pk, "chef"),
        {"status": ServiceStatus.DONE.value},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["service"] == "chef"
    assert response.data["status"] == ServiceStatus.DONE.value
    assert BookingServiceCoverage.objects.filter(
        booking=live_booking, service="chef", status=ServiceStatus.DONE.value
    ).exists()


def test_set_status_rejects_unknown_service(
    api_client: APIClient, staff: User, live_booking: Booking
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        _set_status_url(live_booking.pk, "teleport"),
        {"status": ServiceStatus.DONE.value},
        format="json",
    )
    assert response.status_code == 400
    assert not BookingServiceCoverage.objects.filter(booking=live_booking).exists()


def test_set_status_rejects_unknown_status(
    api_client: APIClient, staff: User, live_booking: Booking
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        _set_status_url(live_booking.pk, "chef"),
        {"status": "banana"},
        format="json",
    )
    assert response.status_code == 400
    assert not BookingServiceCoverage.objects.filter(booking=live_booking).exists()


def test_set_status_forbidden_for_viewer(
    api_client: APIClient, viewer: User, live_booking: Booking
) -> None:
    api_client.force_login(viewer)
    response = api_client.post(
        _set_status_url(live_booking.pk, "chef"),
        {"status": ServiceStatus.DONE.value},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "days_from, days_to, mutate",
    [
        # Departed: already checked out by date.
        (-20, -10, None),
        # Terminal: cancelled.
        (30, 37, lambda b: b.cancel("test")),
        # Archived.
        (50, 57, lambda b: (b.cancel("test"), b.archive())),
    ],
)
def test_set_status_404_for_non_live_booking(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    days_from: int,
    days_to: int,
    mutate: object,
) -> None:
    """Writes resolve through the live scope: non-live bookings 404, no row written."""
    booking = _make_booking(
        guest=guest,
        gbp=gbp,
        terms=terms,
        property_=property_,
        days_from=days_from,
        days_to=days_to,
    )
    if mutate is not None:
        mutate(booking)  # type: ignore[operator]
    api_client.force_login(staff)
    response = api_client.post(
        _set_status_url(booking.pk, "chef"),
        {"status": ServiceStatus.DONE.value},
        format="json",
    )
    assert response.status_code == 404
    assert not BookingServiceCoverage.objects.filter(booking=booking).exists()
