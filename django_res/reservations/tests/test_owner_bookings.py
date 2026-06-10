"""Redaction-matrix tests for the owner bookings endpoint (privacy-critical)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from accounts.models import User
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
from properties.models import Country, Property
from properties.models.finance import PropertyFinance
from reservations.enums import BookingStatus, PaymentMethod
from reservations.models import (
    Booking,
    BookingChargeItem,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/owner/bookings"
_SNAPSHOT = {"total": "1400.00", "commission": "200.00", "tax": "100.00"}


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _make_booking(
    *,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
    guest: Guest,
    rental_price: str = "1400.00",
    status: str = BookingStatus.BALANCE_PAID.value,
    snapshot: dict[str, str] | None = None,
    date_from: date | None = None,
) -> Booking:
    date_from = date_from or (timezone.localdate() - timedelta(days=1))
    date_to = date_from + timedelta(days=7)
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
        date_from=date_from,
        date_to=date_to,
        adults=2,
        total=Decimal(rental_price),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
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


def _owner(org: OwnerOrganisation) -> User:
    user = cast(User, UserFactory())
    OwnerMembershipFactory(organisation=org, user=user, status=OwnerMembershipStatus.ACTIVE)
    return user


def _grant(org: OwnerOrganisation, prop: Property, **flags: bool) -> None:
    OwnerOrgPropertyFactory(organisation=org, property=prop, **flags)


def test_staff_non_owner_gets_403(api_client: APIClient) -> None:
    api_client.force_authenticate(cast(User, UserFactory(role=StaffRole.RESERVATIONS)))
    assert api_client.get(LIST_URL).status_code == 403


def test_list_scoped_to_granted_properties(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_)
    _make_booking(property_=property_, gbp=gbp, terms=terms, guest=guest)
    # A booking on a villa the owner has no grant for.
    other = cast(Property, PropertyFactory())
    leaked = _make_booking(property_=other, gbp=gbp, terms=terms, guest=guest)

    api_client.force_authenticate(user)
    body = api_client.get(LIST_URL).json()
    ids = [row["id"] for row in body["results"]]
    assert leaked.id not in ids
    assert len(ids) == 1


def test_detail_of_ungranted_booking_404s(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    other = cast(Property, PropertyFactory())
    leaked = _make_booking(property_=other, gbp=gbp, terms=terms, guest=guest)

    api_client.force_authenticate(user)
    assert api_client.get(f"{LIST_URL}/{leaked.id}").status_code == 404


def _detail(api_client: APIClient, booking: Booking) -> dict[str, Any]:
    return api_client.get(f"{LIST_URL}/{booking.id}").json()


def test_money_hidden_without_full_money_grant(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=False)
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, guest=guest, snapshot=_SNAPSHOT
    )

    api_client.force_authenticate(user)
    row = api_client.get(LIST_URL).json()["results"][0]
    assert "rental_price" not in row
    assert "balance_due" not in row

    detail = _detail(api_client, booking)
    for key in ("gross_total", "commission", "net_to_owner", "rental_price"):
        assert key not in detail


def test_money_shown_with_full_money_grant(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=True)
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, guest=guest, snapshot=_SNAPSHOT
    )

    api_client.force_authenticate(user)
    row = api_client.get(LIST_URL).json()["results"][0]
    assert row["rental_price"] == "1400.00"

    detail = _detail(api_client, booking)
    assert detail["gross_total"] == "1400.00"
    assert detail["commission"] == "200.00"
    assert detail["net_to_owner"] == "1100.00"


def test_detail_money_includes_charge_owner_effect_percent_commission(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    """Owner detail money must agree with the staff API once charges exist.

    Legacy-style accounting: charges enter the commissionable base. With
    12.5% commission, a +200 charge adds 25.00 commission and 175.00 to
    owner net; gross grows by the full 200.
    """
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=True)
    PropertyFinance.objects.create(
        property=property_,
        commission_calculation_type=CommissionCalcType.PERCENT.value,
        commission_amount=Decimal("12.50"),
    )
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, guest=guest, snapshot=_SNAPSHOT
    )
    BookingChargeItem.objects.create(
        booking=booking, label="Late checkout", amount=Decimal("200.00"), currency=gbp
    )

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["gross_total"] == "1600.00"
    assert detail["commission"] == "225.00"
    assert detail["net_to_owner"] == "1275.00"


def test_detail_money_charges_flow_to_owner_without_commission_config(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    """No PropertyFinance row → charges flow to the owner in full."""
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=True)
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, guest=guest, snapshot=_SNAPSHOT
    )
    BookingChargeItem.objects.create(
        booking=booking, label="Heating", amount=Decimal("200.00"), currency=gbp
    )

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["gross_total"] == "1600.00"
    assert detail["commission"] == "200.00"
    assert detail["net_to_owner"] == "1300.00"


def test_guest_contact_hidden_by_default(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_guest_details=False)
    booking = _make_booking(property_=property_, gbp=gbp, terms=terms, guest=guest)

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert "guest_contact" not in detail
    # The email/phone must not appear under any key.
    assert guest.email and guest.email not in str(detail)


def test_guest_contact_shown_with_grant(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_guest_details=True)
    booking = _make_booking(property_=property_, gbp=gbp, terms=terms, guest=guest)

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["guest_contact"]["email"] == guest.email
    assert detail["guest_contact"]["phone"] == guest.phone


def test_guest_always_named_with_country_and_repeat(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    greece, _ = Country.objects.get_or_create(
        iso2="GR", defaults={"name": "Greece", "iso3": "GRC", "sort_order": 300}
    )
    guest.country = greece
    guest.save(update_fields=["country"])
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_)  # no flags → fully hidden money + contact
    today = timezone.localdate()
    # Two non-overlapping bookings for the same guest on the villa → repeat.
    _make_booking(
        property_=property_, gbp=gbp, terms=terms, guest=guest, date_from=today - timedelta(days=40)
    )
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, guest=guest, date_from=today - timedelta(days=20)
    )

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["guest_name"] == f"{guest.first_name} {guest.last_name}"
    assert detail["guest_country"] == {"code": "GR", "name": "Greece"}
    assert detail["is_repeat_guest"] is True
    # Internal channels never present without the grant.
    assert "guest_contact" not in detail
    assert "notes" not in detail


def test_co_owned_villa_or_merges_money_visibility(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    """A villa co-owned via two orgs: the money-granting org wins (OR-merge)."""
    org_a = cast(OwnerOrganisation, OwnerOrganisationFactory())
    org_b = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = cast(User, UserFactory())
    OwnerMembershipFactory(organisation=org_a, user=user, status=OwnerMembershipStatus.ACTIVE)
    OwnerMembershipFactory(organisation=org_b, user=user, status=OwnerMembershipStatus.ACTIVE)
    _grant(org_a, property_, view_full_money=False)
    _grant(org_b, property_, view_full_money=True)
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, guest=guest, snapshot=_SNAPSHOT
    )

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["net_to_owner"] == "1100.00"


def test_list_query_budget(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    from core.tests import assert_max_queries

    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=True)
    today = timezone.localdate()
    for i in range(5):
        _make_booking(
            property_=property_,
            gbp=gbp,
            terms=terms,
            guest=guest,
            snapshot=_SNAPSHOT,
            date_from=today - timedelta(days=10 * (i + 1)),
        )

    api_client.force_authenticate(user)
    with assert_max_queries(12):
        api_client.get(LIST_URL)
