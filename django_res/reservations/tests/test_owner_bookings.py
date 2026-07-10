"""Redaction-matrix tests for the owner bookings endpoint (privacy-critical)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import CustomerPersonFactory, UserFactory
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
from properties.models import Country, Property
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
    person: Person,
    rental_price: str = "1400.00",
    status: str = BookingStatus.BALANCE_PAID.value,
    snapshot: dict[str, str] | None = None,
    date_from: date | None = None,
) -> Booking:
    date_from = date_from or (timezone.localdate() - timedelta(days=1))
    date_to = date_from + timedelta(days=7)
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
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_)
    _make_booking(property_=property_, gbp=gbp, terms=terms, person=customer)
    # A booking on a villa the owner has no grant for.
    other = cast(Property, PropertyFactory())
    leaked = _make_booking(property_=other, gbp=gbp, terms=terms, person=customer)

    api_client.force_authenticate(user)
    body = api_client.get(LIST_URL).json()
    ids = [row["id"] for row in body["results"]]
    assert leaked.id not in ids
    assert len(ids) == 1


def test_detail_of_ungranted_booking_404s(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    other = cast(Property, PropertyFactory())
    leaked = _make_booking(property_=other, gbp=gbp, terms=terms, person=customer)

    api_client.force_authenticate(user)
    assert api_client.get(f"{LIST_URL}/{leaked.id}").status_code == 404


def _detail(api_client: APIClient, booking: Booking) -> dict[str, Any]:
    return api_client.get(f"{LIST_URL}/{booking.id}").json()


def test_money_hidden_without_full_money_grant(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=False)
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, person=customer, snapshot=_SNAPSHOT
    )

    api_client.force_authenticate(user)
    row = api_client.get(LIST_URL).json()["results"][0]
    assert "rental_price" not in row
    assert "balance_due" not in row

    detail = _detail(api_client, booking)
    for key in ("gross_total", "commission", "net_to_owner", "rental_price"):
        assert key not in detail


def test_money_shown_with_full_money_grant(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=True)
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, person=customer, snapshot=_SNAPSHOT
    )

    api_client.force_authenticate(user)
    row = api_client.get(LIST_URL).json()["results"][0]
    assert row["rental_price"] == "1400.00"

    detail = _detail(api_client, booking)
    assert detail["gross_total"] == "1400.00"
    assert detail["commission"] == "200.00"
    assert detail["net_to_owner"] == "1100.00"


def test_detail_money_includes_charge_owner_effect_percent_commission(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
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
        property_=property_, gbp=gbp, terms=terms, person=customer, snapshot=_SNAPSHOT
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
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    """No PropertyFinance row → charges flow to the owner in full."""
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=True)
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, person=customer, snapshot=_SNAPSHOT
    )
    BookingChargeItem.objects.create(
        booking=booking, label="Heating", amount=Decimal("200.00"), currency=gbp
    )

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["gross_total"] == "1600.00"
    assert detail["commission"] == "200.00"
    assert detail["net_to_owner"] == "1300.00"


def test_detail_money_non_commissionable_charge_passes_through(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    """GAP-076: a non-commissionable charge adds no commission — the owner
    receives it in full even under percent commission."""
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=True)
    PropertyFinance.objects.create(
        property=property_,
        commission_calculation_type=CommissionCalcType.PERCENT.value,
        commission_amount=Decimal("12.50"),
    )
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, person=customer, snapshot=_SNAPSHOT
    )
    BookingChargeItem.objects.create(
        booking=booking,
        label="Pool heating",
        amount=Decimal("200.00"),
        currency=gbp,
        commissionable=False,
    )

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["gross_total"] == "1600.00"
    assert detail["commission"] == "200.00"  # snapshot commission only
    assert detail["net_to_owner"] == "1300.00"  # 1100 + 200 pass-through


def test_detail_money_mixed_charges_split_per_line(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    """GAP-076: only the commissionable line feeds the percent skim."""
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=True)
    PropertyFinance.objects.create(
        property=property_,
        commission_calculation_type=CommissionCalcType.PERCENT.value,
        commission_amount=Decimal("12.50"),
    )
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, person=customer, snapshot=_SNAPSHOT
    )
    BookingChargeItem.objects.create(
        booking=booking, label="Late checkout", amount=Decimal("200.00"), currency=gbp
    )
    BookingChargeItem.objects.create(
        booking=booking,
        label="Chef",
        amount=Decimal("100.00"),
        currency=gbp,
        commissionable=False,
    )

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["gross_total"] == "1700.00"  # 1400 + 200 + 100
    assert detail["commission"] == "225.00"  # 200 + 12.5% of 200 only
    assert detail["net_to_owner"] == "1375.00"  # 1100 + 175 + 100


def test_guest_contact_hidden_by_default(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_guest_details=False)
    booking = _make_booking(property_=property_, gbp=gbp, terms=terms, person=customer)

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert "guest_contact" not in detail
    # The email/phone must not appear under any key.
    email = customer.primary_email()
    assert email
    assert email not in str(detail)


def test_guest_contact_shown_with_grant(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, property_: Property
) -> None:
    # A customer carrying an email but NO phone — pins that an absent channel is
    # value-gated to null by the person-first contact helpers (3c-2a).
    person = cast(Person, CustomerPersonFactory(primary_email="ada@example.com", primary_phone=""))
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_guest_details=True)
    booking = _make_booking(property_=property_, gbp=gbp, terms=terms, person=person)

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["guest_contact"]["email"] == person.primary_email()
    assert detail["guest_contact"]["phone"] is None


def test_guest_always_named_with_country_and_repeat(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    greece, _ = Country.objects.get_or_create(
        iso2="GR", defaults={"name": "Greece", "iso3": "GRC", "sort_order": 300}
    )
    customer.country = greece
    customer.save(update_fields=["country"])
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_)  # no flags → fully hidden money + contact
    today = timezone.localdate()
    # Two non-overlapping bookings for the same customer on the villa → repeat.
    _make_booking(
        property_=property_,
        gbp=gbp,
        terms=terms,
        person=customer,
        date_from=today - timedelta(days=40),
    )
    booking = _make_booking(
        property_=property_,
        gbp=gbp,
        terms=terms,
        person=customer,
        date_from=today - timedelta(days=20),
    )

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["guest_name"] == f"{customer.first_name} {customer.last_name}"
    assert detail["guest_country"] == {"code": "GR", "name": "Greece"}
    assert detail["is_repeat_guest"] is True
    # Internal channels never present without the grant.
    assert "guest_contact" not in detail
    assert "notes" not in detail


def test_repeat_guest_detected_on_person_only_bookings(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    """GAP-045 3d-C regression: repeat detection is keyed on `person_id`, so it
    still fires for bookings carrying only the `person` FK — the state every
    booking is born in. A guest-keyed `OuterRef` join would have been NULL=NULL →
    never a match, silently breaking owner repeat-guest detection.
    """
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_)
    today = timezone.localdate()
    _make_booking(
        property_=property_,
        gbp=gbp,
        terms=terms,
        person=customer,
        date_from=today - timedelta(days=40),
    )
    booking = _make_booking(
        property_=property_,
        gbp=gbp,
        terms=terms,
        person=customer,
        date_from=today - timedelta(days=20),
    )

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["is_repeat_guest"] is True


def test_co_owned_villa_or_merges_money_visibility(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
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
        property_=property_, gbp=gbp, terms=terms, person=customer, snapshot=_SNAPSHOT
    )

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["net_to_owner"] == "1100.00"


def test_list_query_budget(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
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
            person=customer,
            snapshot=_SNAPSHOT,
            date_from=today - timedelta(days=10 * (i + 1)),
        )

    api_client.force_authenticate(user)
    with assert_max_queries(12):
        api_client.get(LIST_URL)


# ---------------------------------------------------------------------------
# GAP-045 Unit 3c-2c — owner reads resolve person-first, guest fallback
# ---------------------------------------------------------------------------


def _grace(*, country: Country | None = None) -> Person:
    """A customer Person (Grace Hopper, grace@navy.mil, +15125550100) — the read
    source the owner serializer resolves from (person-first, the guest leg gone)."""
    from accounts.enums import PhoneLabel
    from accounts.models import PersonPhone

    person = cast(
        Person,
        CustomerPersonFactory(
            first_name="Grace",
            last_name="Hopper",
            primary_email="grace@navy.mil",
            primary_phone="",
        ),
    )
    if country is not None:
        person.country = country
        person.save(update_fields=["country", "updated_at"])
    PersonPhone.objects.create(
        contact=person, number="+15125550100", label=PhoneLabel.MOBILE.value, is_primary=True
    )
    return person


def test_owner_detail_reads_person_name_and_contact(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_guest_details=True)
    booking = _make_booking(property_=property_, gbp=gbp, terms=terms, person=_grace())

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["guest_name"] == "Grace Hopper"
    assert detail["guest_contact"]["email"] == "grace@navy.mil"
    assert detail["guest_contact"]["phone"] == "+15125550100"


def test_owner_reads_person_country(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, property_: Property
) -> None:
    # GAP-045 3d-3: the owner serializer resolves country solely from the Person
    # (the guest leg is gone), so the person's country is what shows.
    france, _ = Country.objects.get_or_create(
        iso2="FR", defaults={"name": "France", "iso3": "FRA", "sort_order": 301}
    )
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_)  # no flags → contact hidden, name + country still shown
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, person=_grace(country=france)
    )

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert detail["guest_country"] == {"code": "FR", "name": "France"}


def test_owner_guest_contact_absent_for_anonymized_customer(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, property_: Property
) -> None:
    """An anonymized customer leaks no channel: ``Person.primary_email/phone``
    fail closed on ANONYMIZED, so the source is empty and ``guest_contact`` is
    omitted entirely (matching the no-grant redaction tests)."""
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_guest_details=True)
    person = _grace()
    booking = _make_booking(property_=property_, gbp=gbp, terms=terms, person=person)
    person.anonymize()

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)
    assert "guest_contact" not in detail
    assert "grace@navy.mil" not in str(detail)


def test_owner_list_person_reads_stay_within_query_budget(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, property_: Property
) -> None:
    """The person join + email/phone prefetch keep the owner list at a constant
    budget regardless of how many person-linked bookings it returns."""
    from core.tests import assert_max_queries

    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_guest_details=True)
    today = timezone.localdate()
    for i in range(4):
        person = cast(
            Person,
            CustomerPersonFactory(
                first_name="Extra",
                last_name="Guest",
                primary_email=f"owner-extra{i}@example.com",
            ),
        )
        _make_booking(
            property_=property_,
            gbp=gbp,
            terms=terms,
            person=person,
            date_from=today - timedelta(days=10 * (i + 1)),
        )

    api_client.force_authenticate(user)
    with assert_max_queries(12):
        response = api_client.get(LIST_URL)
    assert len(response.json()["results"]) == 4


# ---------------------------------------------------------------------------
# GAP-077 — per-component payment splits on the owner booking DETAIL only.
# Same derive-on-read service as the staff API; gated by `view_full_money`;
# never on the list path (its query budget is pinned above).
# ---------------------------------------------------------------------------


def _schedule_payment(booking: Booking, *, purpose: str, amount: str) -> None:
    from payments.enums import PaymentStatus
    from payments.models import Payment

    Payment.objects.create(
        booking=booking,
        purpose=purpose,
        status=PaymentStatus.PENDING.value,
        amount=Decimal(amount),
        currency=booking.currency,
    )


def test_detail_payment_splits_render_and_sum(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=True)
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, person=customer, snapshot=_SNAPSHOT
    )
    _schedule_payment(booking, purpose="deposit", amount="420.00")
    _schedule_payment(booking, purpose="balance", amount="980.00")

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)

    splits = detail["payment_splits"]
    assert [s["purpose"] for s in splits] == ["deposit", "balance"]
    deposit, balance = splits
    # 200 commission / 100 tax allocated 30/70 by gross share.
    assert deposit["gross"] == "420.00"
    assert deposit["commission"] == "60.00"
    assert deposit["tax"] == "30.00"
    assert deposit["net_to_owner"] == "330.00"
    assert deposit["status"] == "pending"
    assert deposit["due_at"] is None
    assert balance["gross"] == "980.00"
    assert balance["commission"] == "140.00"
    assert balance["tax"] == "70.00"
    assert balance["net_to_owner"] == "770.00"
    assert sum(Decimal(s["net_to_owner"]) for s in splits) == Decimal(detail["net_to_owner"])


def test_detail_payment_splits_hidden_without_money_grant(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=False)
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, person=customer, snapshot=_SNAPSHOT
    )
    _schedule_payment(booking, purpose="deposit", amount="420.00")

    api_client.force_authenticate(user)
    detail = _detail(api_client, booking)

    assert "payment_splits" not in detail


def test_list_never_includes_payment_splits(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    """Splits are detail-only — the list path has no payments prefetch and a
    pinned query budget, so the key must never appear there."""
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=True)
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, person=customer, snapshot=_SNAPSHOT
    )
    _schedule_payment(booking, purpose="deposit", amount="420.00")

    api_client.force_authenticate(user)
    rows = api_client.get(LIST_URL).json()["results"]

    assert rows and all("payment_splits" not in row for row in rows)


def test_detail_query_budget_with_splits(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, customer: Person, property_: Property
) -> None:
    """The detail path prefetches payments + charge annotations + finance, so
    the splits render stays inside a constant budget."""
    from core.tests import assert_max_queries

    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    _grant(org, property_, view_full_money=True)
    booking = _make_booking(
        property_=property_, gbp=gbp, terms=terms, person=customer, snapshot=_SNAPSHOT
    )
    BookingChargeItem.objects.create(
        booking=booking, label="Chef", amount=Decimal("100.00"), currency=gbp
    )
    _schedule_payment(booking, purpose="deposit", amount="450.00")
    _schedule_payment(booking, purpose="balance", amount="1050.00")

    api_client.force_authenticate(user)
    with assert_max_queries(12):
        detail = _detail(api_client, booking)
    assert len(detail["payment_splits"]) == 2
