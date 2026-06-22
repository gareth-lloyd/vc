"""API tests for GET /owner/properties/{id}/calendar."""

from __future__ import annotations

from datetime import timedelta
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
from properties.factories import PropertyFactory
from properties.models import Property
from reservations.enums import BookingStatus, PaymentMethod
from reservations.models import Booking, Quotation, QuotationLine, TermsVersion

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _owner(org: OwnerOrganisation) -> User:
    user = cast(User, UserFactory())
    OwnerMembershipFactory(organisation=org, user=user, status=OwnerMembershipStatus.ACTIVE)
    return user


def _booking_on(property_: Property, gbp: Currency, terms: TermsVersion, person: Person) -> Booking:
    start = timezone.localdate() + timedelta(days=10)
    end = start + timedelta(days=7)
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
        date_from=start,
        date_to=end,
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        person=person,
        property=property_,
        date_from=start,
        date_to=end,
        adults=2,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
        status=BookingStatus.BALANCE_PAID.value,
    )


def _url(property_id: int) -> str:
    today = timezone.localdate()
    return (
        f"/api/v1/owner/properties/{property_id}/calendar"
        f"?from={today.isoformat()}&to={(today + timedelta(days=30)).isoformat()}"
    )


def test_staff_non_owner_gets_403(api_client: APIClient, property_: Property) -> None:
    api_client.force_authenticate(cast(User, UserFactory(role=StaffRole.RESERVATIONS)))
    assert api_client.get(_url(property_.id)).status_code == 403


def test_ungranted_property_404s(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    other = cast(Property, PropertyFactory())
    api_client.force_authenticate(user)
    assert api_client.get(_url(other.id)).status_code == 404


def test_missing_range_400s(api_client: APIClient, property_: Property) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    OwnerOrgPropertyFactory(organisation=org, property=property_)
    api_client.force_authenticate(user)
    resp = api_client.get(f"/api/v1/owner/properties/{property_.id}/calendar")
    assert resp.status_code == 400


def test_booked_cells_carry_no_guest_identity(
    api_client: APIClient,
    gbp: Currency,
    terms: TermsVersion,
    customer: Person,
    property_: Property,
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    OwnerOrgPropertyFactory(organisation=org, property=property_, view_full_money=True)
    _booking_on(property_, gbp, terms, customer)

    api_client.force_authenticate(user)
    body = api_client.get(_url(property_.id)).json()
    assert body["property_id"] == property_.id

    booked = [c for c in body["cells"] if c["reason"] == "booked"]
    assert booked, "expected the booking to mark some cells booked"
    for cell in booked:
        assert cell["available"] is False
        # Internal hold id and any guest identity must be absent.
        assert "block_id" not in cell
    # Guest PII never appears anywhere in the calendar payload.
    email = customer.primary_email()
    assert email and email not in str(body)
    assert customer.last_name not in str(body)
