"""API tests for GET /owner/dashboard (lives in reservations — reads Bookings)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import cast

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from accounts.models import Person, User
from core.enums import StaffRole
from owners.enums import OwnerMembershipStatus
from owners.factories import (
    OwnerMembershipFactory,
    OwnerOrganisationFactory,
    OwnerOrgPropertyFactory,
)
from owners.models import OwnerOrganisation
from pricing.models import Currency
from properties.enums import CommissionCalcType
from properties.factories import PropertyFactory
from properties.models import Property
from properties.models.finance import PropertyFinance
from reservations.enums import BookingStatus, PaymentMethod
from reservations.models import (
    Booking,
    BookingChargeItem,
    Quotation,
    QuotationLine,
    TermsVersion,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/owner/dashboard"


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _make_booking(
    *,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
    customer: Person,
    date_from: date,
    rental_price: str,
    status: str,
    snapshot: dict[str, str] | None = None,
) -> Booking:
    date_to = date_from + timedelta(days=7)
    person = customer
    quotation = Quotation.objects.create(
        enquiry=person.enquiries_as_customer.create(),
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
        total=Decimal(rental_price),
    )
    return Booking.objects.create(
        quotation_line=line,
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
        rental_price=Decimal(rental_price),
        balance_due=Decimal(rental_price),
        status=status,
        pricing_snapshot=snapshot or {},
    )


def _owner_with_full_money_grant(property_: Property) -> User:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = cast(User, UserFactory())
    OwnerMembershipFactory(organisation=org, user=user, status=OwnerMembershipStatus.ACTIVE)
    OwnerOrgPropertyFactory(organisation=org, property=property_, view_full_money=True)
    return user


def test_staff_non_owner_gets_403(api_client: APIClient) -> None:
    api_client.force_authenticate(cast(User, UserFactory(role=StaffRole.RESERVATIONS)))
    assert api_client.get(URL).status_code == 403


def test_dashboard_aggregates_scoped_bookings_only(
    api_client: APIClient,
    gbp: Currency,
    terms: TermsVersion,
    customer: Person,
    property_: Property,
) -> None:
    user = _owner_with_full_money_grant(property_)
    today = timezone.localdate()
    snapshot = {"total": "1400.00", "commission": "200.00", "tax": "100.00"}
    # Two YTD bookings on the granted villa.
    _make_booking(
        property_=property_,
        gbp=gbp,
        terms=terms,
        customer=customer,
        date_from=date(today.year, 1, 10),
        rental_price="1400.00",
        status=BookingStatus.BALANCE_PAID.value,
        snapshot=snapshot,
    )
    _make_booking(
        property_=property_,
        gbp=gbp,
        terms=terms,
        customer=customer,
        date_from=today - timedelta(days=2),
        rental_price="1000.00",
        status=BookingStatus.DEPOSIT_PAID.value,
        snapshot=snapshot,
    )
    # A booking on an ungranted property must not leak into the totals.
    other = cast(Property, PropertyFactory())
    _make_booking(
        property_=other,
        gbp=gbp,
        terms=terms,
        customer=customer,
        date_from=date(today.year, 1, 5),
        rental_price="9999.00",
        status=BookingStatus.BALANCE_PAID.value,
    )

    api_client.force_authenticate(user)
    body = api_client.get(URL).json()

    assert body["ytd"]["bookings"] == 2
    assert body["ytd"]["gross_revenue"] == "2400.00"
    # net = total - commission - tax = 1100 per booking, times 2.
    assert body["ytd"]["net_to_owner"] == "2200.00"
    assert body["properties"]["total"] == 1


def test_ytd_net_includes_charge_owner_effect(
    api_client: APIClient,
    gbp: Currency,
    terms: TermsVersion,
    customer: Person,
    property_: Property,
) -> None:
    """The YTD net KPI must agree with the per-booking owner detail once
    manual charges exist: a +200 charge under 12.5% commission adds 175.00
    to owner net. Gross revenue stays rental-price-based (charges are
    extras, not rent).
    """
    user = _owner_with_full_money_grant(property_)
    PropertyFinance.objects.create(
        property=property_,
        commission_calculation_type=CommissionCalcType.PERCENT.value,
        commission_amount=Decimal("12.50"),
    )
    booking = _make_booking(
        property_=property_,
        gbp=gbp,
        terms=terms,
        customer=customer,
        date_from=date(timezone.localdate().year, 1, 10),
        rental_price="1400.00",
        status=BookingStatus.BALANCE_PAID.value,
        snapshot={"total": "1400.00", "commission": "200.00", "tax": "100.00"},
    )
    BookingChargeItem.objects.create(
        booking=booking, label="Late checkout", amount=Decimal("200.00"), currency=gbp
    )

    api_client.force_authenticate(user)
    body = api_client.get(URL).json()
    # net = (1400 - 200 - 100) + (200 - 25) = 1275
    assert body["ytd"]["net_to_owner"] == "1275.00"
    assert body["ytd"]["gross_revenue"] == "1400.00"


def test_net_is_null_without_full_money_grant(
    api_client: APIClient,
    gbp: Currency,
    terms: TermsVersion,
    customer: Person,
    property_: Property,
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = cast(User, UserFactory())
    OwnerMembershipFactory(organisation=org, user=user, status=OwnerMembershipStatus.ACTIVE)
    OwnerOrgPropertyFactory(organisation=org, property=property_, view_full_money=False)
    _make_booking(
        property_=property_,
        gbp=gbp,
        terms=terms,
        customer=customer,
        date_from=timezone.localdate() - timedelta(days=1),
        rental_price="1400.00",
        status=BookingStatus.BALANCE_PAID.value,
        snapshot={"total": "1400.00", "commission": "200.00", "tax": "100.00"},
    )

    api_client.force_authenticate(user)
    body = api_client.get(URL).json()
    # No view_full_money grant → both money KPIs are withheld, but the
    # operational booking count is still shown.
    assert body["ytd"]["net_to_owner"] is None
    assert body["ytd"]["gross_revenue"] is None
    assert body["ytd"]["bookings"] == 1


def test_gross_revenue_only_sums_full_money_properties(
    api_client: APIClient,
    gbp: Currency,
    terms: TermsVersion,
    customer: Person,
    property_: Property,
) -> None:
    """Mixed grants: gross/net reflect only the view_full_money villa."""
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = cast(User, UserFactory())
    OwnerMembershipFactory(organisation=org, user=user, status=OwnerMembershipStatus.ACTIVE)
    visible = property_
    hidden = cast(Property, PropertyFactory())
    OwnerOrgPropertyFactory(organisation=org, property=visible, view_full_money=True)
    OwnerOrgPropertyFactory(organisation=org, property=hidden, view_full_money=False)
    today = timezone.localdate()
    _make_booking(
        property_=visible,
        gbp=gbp,
        terms=terms,
        customer=customer,
        date_from=date(today.year, 1, 10),
        rental_price="1400.00",
        status=BookingStatus.BALANCE_PAID.value,
        snapshot={"total": "1400.00", "commission": "200.00", "tax": "100.00"},
    )
    _make_booking(
        property_=hidden,
        gbp=gbp,
        terms=terms,
        customer=customer,
        date_from=date(today.year, 1, 12),
        rental_price="5000.00",
        status=BookingStatus.BALANCE_PAID.value,
    )

    api_client.force_authenticate(user)
    body = api_client.get(URL).json()
    # The hidden villa's 5000 must not appear in the gross figure.
    assert body["ytd"]["gross_revenue"] == "1400.00"
    assert body["ytd"]["bookings"] == 2  # count is operational — both villas


def test_upcoming_arrivals_window_and_naming(
    api_client: APIClient,
    gbp: Currency,
    terms: TermsVersion,
    customer: Person,
    property_: Property,
) -> None:
    user = _owner_with_full_money_grant(property_)
    today = timezone.localdate()
    _make_booking(
        property_=property_,
        gbp=gbp,
        terms=terms,
        customer=customer,
        date_from=today + timedelta(days=5),
        rental_price="1400.00",
        status=BookingStatus.BALANCE_PAID.value,
    )
    # Outside the 30-day window — excluded.
    _make_booking(
        property_=property_,
        gbp=gbp,
        terms=terms,
        customer=customer,
        date_from=today + timedelta(days=60),
        rental_price="1400.00",
        status=BookingStatus.BALANCE_PAID.value,
    )

    api_client.force_authenticate(user)
    body = api_client.get(URL).json()
    arrivals = body["upcoming_arrivals"]
    assert len(arrivals) == 1
    assert arrivals[0]["guest_name"] == f"{customer.first_name} {customer.last_name}"
    assert "guest_contact" not in arrivals[0]


def test_upcoming_arrivals_name_reads_person_first(
    api_client: APIClient,
    gbp: Currency,
    terms: TermsVersion,
    customer: Person,
    property_: Property,
) -> None:
    """GAP-045 Unit 3c-2c: the arrivals name resolves from the booking's Person."""
    user = _owner_with_full_money_grant(property_)
    today = timezone.localdate()
    _make_booking(
        property_=property_,
        gbp=gbp,
        terms=terms,
        customer=customer,
        date_from=today + timedelta(days=5),
        rental_price="1400.00",
        status=BookingStatus.BALANCE_PAID.value,
    )
    customer.first_name = "Grace"
    customer.last_name = "Hopper"
    customer.save(update_fields=["first_name", "last_name", "updated_at"])

    api_client.force_authenticate(user)
    body = api_client.get(URL).json()
    assert body["upcoming_arrivals"][0]["guest_name"] == "Grace Hopper"
