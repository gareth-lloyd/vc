"""API tests for the Clients (renter) directory list.

`GAP-047` + `GAP-053`: `GET /api/v1/clients` is a query-pinned list over
`accounts.Person`. Membership is customers PLUS agent-capacity people (belong to
an agency, or deal through an agent — agents fold into Clients, no separate
page). Annotated with the agent-capacity `is_agent` flag, the `is_repeat_customer`
(>=1 booking) flag, and quoted/booked region rollups. Hosted from
`reservations/urls.py` — `accounts` is the bottom of the import spine and cannot
serialise reservations rows (precedent: `contact_reads.py`).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import CustomerPersonFactory, PersonFactory
from accounts.models import Person, User
from core.enums import StaffRole
from core.tests import assert_max_queries
from pricing.models import Currency
from properties.factories import PropertyFactory
from properties.models import Property
from reservations.enums import (
    QUOTED_STATUSES,
    UNREALISED_BOOKING_STATUSES,
    BookingStatus,
    PaymentMethod,
    QuotationStatus,
)
from reservations.models import Booking, Enquiry, Quotation, QuotationLine, TermsVersion


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True, email="staff@example.com", password="x", role=StaffRole.RESERVATIONS
    )


def _customer(**kwargs: object) -> Person:
    return cast(Person, CustomerPersonFactory(**kwargs))


def _agent() -> Person:
    """A business contact used as the `.agent` on a deal."""
    return cast(Person, PersonFactory())


def _property(slug: str) -> Property:
    return cast(Property, PropertyFactory(region__slug=slug))


def _quote(
    *,
    person: Person,
    terms: TermsVersion,
    status: str,
    agent: Person | None = None,
    property_: Property | None = None,
    gbp: Currency | None = None,
) -> Quotation:
    """A quote for `person`; with `property_`/`gbp` it also carries one line (so
    its region counts toward the quoted-regions aggregation)."""
    enquiry = Enquiry.objects.create(person=person, first_name="Q", adults=2)
    quote = Quotation.objects.create(
        enquiry=enquiry,
        person=person,
        agent=agent,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
        status=status,
    )
    if property_ is not None:
        assert gbp is not None, "pass gbp when property_ is set (the line needs a currency)"
        QuotationLine.objects.create(
            quotation=quote,
            property=property_,
            currency=gbp,
            date_from=date(2026, 6, 10),
            date_to=date(2026, 6, 17),
            adults=2,
            children=0,
            total=Decimal("1400.00"),
            is_selected=True,
        )
    return quote


def _booking(
    *,
    person: Person,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
    status: str = BookingStatus.DEPOSIT_PAID.value,
    agent: Person | None = None,
) -> Booking:
    quote = _quote(
        person=person,
        terms=terms,
        status=QuotationStatus.ACCEPTED.value,
        property_=property_,
        gbp=gbp,
    )
    return Booking.objects.create(
        quotation_line=quote.lines.get(),
        person=person,
        property=property_,
        agent=agent,
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
        status=status,
        # `booking_cancelled_status_requires_cancelled_at` CHECK constraint.
        cancelled_at=(timezone.now() if status == BookingStatus.CANCELLED.value else None),
    )


@pytest.mark.django_db
def test_lists_only_customers(api_client: APIClient, staff: User) -> None:
    customer = _customer()
    contact = cast(Person, PersonFactory())  # kind=CONTACT (model default)
    api_client.force_login(staff)

    response = api_client.get("/api/v1/clients")

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["results"]}
    assert customer.pk in ids
    assert contact.pk not in ids


@pytest.mark.django_db
def test_row_shape_exposes_primary_channels(api_client: APIClient, staff: User) -> None:
    customer = _customer(primary_email="ada@example.com", primary_phone="+44 7700 900111")
    api_client.force_login(staff)

    response = api_client.get("/api/v1/clients")

    row = next(r for r in response.json()["results"] if r["id"] == customer.pk)
    assert row["primary_email"] == "ada@example.com"
    assert row["primary_phone"] == "+44 7700 900111"
    assert row["is_agent"] is False
    # GAP-053: chip active-state fields.
    assert row["tags"] == []
    assert row["is_repeat_customer"] is False


@pytest.mark.django_db
def test_agency_contact_appears_in_clients(api_client: APIClient, staff: User) -> None:
    # GAP-053: agents fold into Clients (no separate Agents page). A CONTACT who
    # belongs to an agency is agent-capacity and must be reachable here, alongside
    # customers — even with no deals of their own.
    from accounts.factories import OrganisationFactory

    agent_person = cast(Person, PersonFactory(agency=OrganisationFactory()))
    plain_contact = cast(Person, PersonFactory())  # no agency, no deals
    api_client.force_login(staff)

    ids = {r["id"] for r in api_client.get("/api/v1/clients").json()["results"]}

    assert agent_person.pk in ids
    assert plain_contact.pk not in ids


@pytest.mark.django_db
def test_agency_contact_is_agent_capacity(api_client: APIClient, staff: User) -> None:
    # The agency contact reads as is_agent and partitions into capacity=agent.
    from accounts.factories import OrganisationFactory

    agent_person = cast(Person, PersonFactory(agency=OrganisationFactory()))
    api_client.force_login(staff)

    row = next(
        r for r in api_client.get("/api/v1/clients").json()["results"] if r["id"] == agent_person.pk
    )
    assert row["is_agent"] is True

    agent_ids = {
        r["id"] for r in api_client.get("/api/v1/clients?capacity=agent").json()["results"]
    }
    direct_ids = {
        r["id"] for r in api_client.get("/api/v1/clients?capacity=direct").json()["results"]
    }
    assert agent_person.pk in agent_ids
    assert agent_person.pk not in direct_ids


@pytest.mark.django_db
def test_repeat_filter_selects_only_booked_clients(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    # GAP-053: the Repeat chip filters on the derived >=1-booking flag.
    booked = _customer()
    _booking(person=booked, property_=property_, gbp=gbp, terms=terms)
    never = _customer()
    api_client.force_login(staff)

    repeat_ids = {r["id"] for r in api_client.get("/api/v1/clients?repeat=true").json()["results"]}

    assert booked.pk in repeat_ids
    assert never.pk not in repeat_ids
    # The booked client is flagged on its row too.
    results = api_client.get("/api/v1/clients").json()["results"]
    row = next(r for r in results if r["id"] == booked.pk)
    assert row["is_repeat_customer"] is True


@pytest.mark.django_db
def test_tags_filter_overlap(api_client: APIClient, staff: User) -> None:
    # GAP-053: VIP / Trade chips filter via the ?tags= overlap (mirrors /contacts).
    vip = _customer(tags=["vip"])
    trade = _customer(tags=["trade"])
    api_client.force_login(staff)

    vip_ids = {r["id"] for r in api_client.get("/api/v1/clients?tags=vip").json()["results"]}

    assert vip.pk in vip_ids
    assert trade.pk not in vip_ids
    row = next(r for r in api_client.get("/api/v1/clients").json()["results"] if r["id"] == vip.pk)
    assert row["tags"] == ["vip"]


@pytest.mark.django_db
def test_is_agent_true_via_enquiry(api_client: APIClient, staff: User) -> None:
    customer = _customer()
    Enquiry.objects.create(person=customer, agent=_agent(), first_name="E", adults=2)
    api_client.force_login(staff)

    row = next(
        r for r in api_client.get("/api/v1/clients").json()["results"] if r["id"] == customer.pk
    )
    assert row["is_agent"] is True


@pytest.mark.django_db
def test_is_agent_true_via_quote(api_client: APIClient, staff: User, terms: TermsVersion) -> None:
    customer = _customer()
    _quote(person=customer, agent=_agent(), terms=terms, status=QuotationStatus.SENT.value)
    api_client.force_login(staff)

    row = next(
        r for r in api_client.get("/api/v1/clients").json()["results"] if r["id"] == customer.pk
    )
    assert row["is_agent"] is True


@pytest.mark.django_db
def test_is_agent_true_via_booking(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    customer = _customer()
    _booking(person=customer, agent=_agent(), property_=property_, gbp=gbp, terms=terms)
    api_client.force_login(staff)

    row = next(
        r for r in api_client.get("/api/v1/clients").json()["results"] if r["id"] == customer.pk
    )
    assert row["is_agent"] is True


@pytest.mark.django_db
def test_capacity_filter_partitions_direct_and_agent(api_client: APIClient, staff: User) -> None:
    direct = _customer()
    agent_client = _customer()
    Enquiry.objects.create(person=agent_client, agent=_agent(), first_name="E", adults=2)
    api_client.force_login(staff)

    agent_ids = {
        r["id"] for r in api_client.get("/api/v1/clients?capacity=agent").json()["results"]
    }
    direct_ids = {
        r["id"] for r in api_client.get("/api/v1/clients?capacity=direct").json()["results"]
    }

    assert agent_client.pk in agent_ids and direct.pk not in agent_ids
    assert direct.pk in direct_ids and agent_client.pk not in direct_ids


@pytest.mark.django_db
def test_search_matches_name_and_email(api_client: APIClient, staff: User) -> None:
    match = _customer(first_name="Zelda", last_name="Fitz", primary_email="zelda@example.com")
    _customer(first_name="Other", last_name="Person", primary_email="other@example.com")
    api_client.force_login(staff)

    by_name = {r["id"] for r in api_client.get("/api/v1/clients?search=Zelda").json()["results"]}
    by_email = {
        r["id"] for r in api_client.get("/api/v1/clients?search=zelda@example").json()["results"]
    }

    assert by_name == {match.pk}
    assert by_email == {match.pk}


@pytest.mark.django_db
def test_requires_staff(api_client: APIClient) -> None:
    _customer()
    assert api_client.get("/api/v1/clients").status_code in (401, 403)


@pytest.mark.django_db
def test_query_count_is_flat(api_client: APIClient, staff: User, terms: TermsVersion) -> None:
    api_client.force_login(staff)
    _customer()
    with assert_max_queries(8) as one:
        assert api_client.get("/api/v1/clients").status_code == 200

    for _ in range(11):
        c = _customer()
        Enquiry.objects.create(person=c, agent=_agent(), first_name="E", adults=2)
    with assert_max_queries(8) as many:
        assert api_client.get("/api/v1/clients").status_code == 200

    assert len(one.captured_queries) == len(many.captured_queries)


# --------------------------------------------------------------------------
# Unit 2 — quoted/booked region aggregation
# --------------------------------------------------------------------------
def _row_for(api_client: APIClient, person: Person) -> dict[str, Any]:
    results = api_client.get("/api/v1/clients").json()["results"]
    return next(r for r in results if r["id"] == person.pk)


@pytest.mark.django_db
def test_region_slugs_aggregate_quoted_and_booked(
    api_client: APIClient, staff: User, gbp: Currency, terms: TermsVersion
) -> None:
    customer = _customer()
    tuscany = _property("tuscany")
    amalfi = _property("amalfi")
    _quote(
        person=customer, terms=terms, status=QuotationStatus.SENT.value, property_=tuscany, gbp=gbp
    )
    _quote(
        person=customer,
        terms=terms,
        status=QuotationStatus.ACCEPTED.value,
        property_=amalfi,
        gbp=gbp,
    )
    _booking(person=customer, property_=tuscany, gbp=gbp, terms=terms)
    api_client.force_login(staff)

    row = _row_for(api_client, customer)
    assert set(row["quoted_region_slugs"]) == {"tuscany", "amalfi"}
    assert set(row["booked_region_slugs"]) == {"tuscany"}


@pytest.mark.django_db
def test_region_slugs_respect_status_gates(
    api_client: APIClient, staff: User, gbp: Currency, terms: TermsVersion
) -> None:
    customer = _customer()
    draftland = _property("draftland")
    cancelland = _property("cancelland")
    # A DRAFT quote and a CANCELLED booking must not contribute their regions.
    _quote(
        person=customer,
        terms=terms,
        status=QuotationStatus.DRAFT.value,
        property_=draftland,
        gbp=gbp,
    )
    _booking(
        person=customer,
        property_=cancelland,
        gbp=gbp,
        terms=terms,
        status=BookingStatus.CANCELLED.value,
    )
    api_client.force_login(staff)

    row = _row_for(api_client, customer)
    # DRAFT quote → draftland is not a quoted region; CANCELLED booking →
    # cancelland is not a booked region. (cancelland *is* a quoted region: the
    # `_booking` helper creates the customary ACCEPTED quote behind the booking.)
    assert "draftland" not in row["quoted_region_slugs"]
    assert "cancelland" not in row["booked_region_slugs"]


@pytest.mark.django_db
def test_region_slugs_empty_when_no_deals(api_client: APIClient, staff: User) -> None:
    customer = _customer()
    api_client.force_login(staff)

    row = _row_for(api_client, customer)
    assert row["quoted_region_slugs"] == []
    assert row["booked_region_slugs"] == []


def test_region_status_gates_derive_from_enums() -> None:
    # Pin the gates to the enum members so a status rename can't silently drop a
    # region (no DB needed).
    assert QUOTED_STATUSES == (QuotationStatus.SENT.value, QuotationStatus.ACCEPTED.value)
    assert QuotationStatus.DRAFT.value not in QUOTED_STATUSES
    assert UNREALISED_BOOKING_STATUSES == (
        BookingStatus.CANCELLED.value,
        BookingStatus.EXPIRED.value,
        BookingStatus.DECLINED.value,
    )
    # Legacy imports rest at DRAFT and completed stays at CHECKED_OUT — both must
    # count as booked, so neither is in the excluded set.
    assert BookingStatus.DRAFT.value not in UNREALISED_BOOKING_STATUSES
    assert BookingStatus.CHECKED_OUT.value not in UNREALISED_BOOKING_STATUSES


@pytest.mark.django_db
def test_booked_regions_include_legacy_draft_and_completed_bookings(
    api_client: APIClient, staff: User, gbp: Currency, terms: TermsVersion
) -> None:
    # The migration rests imported reservations at DRAFT; a completed stay is
    # CHECKED_OUT. Both are real booked regions and must surface.
    customer = _customer()
    legacy = _property("legacy-region")
    completed = _property("completed-region")
    _booking(
        person=customer, property_=legacy, gbp=gbp, terms=terms, status=BookingStatus.DRAFT.value
    )
    _booking(
        person=customer,
        property_=completed,
        gbp=gbp,
        terms=terms,
        status=BookingStatus.CHECKED_OUT.value,
    )
    api_client.force_login(staff)

    row = _row_for(api_client, customer)
    assert set(row["booked_region_slugs"]) == {"legacy-region", "completed-region"}


@pytest.mark.django_db
def test_quoted_regions_exclude_synthetic_booking_fill_quotes(
    api_client: APIClient, staff: User, gbp: Currency, terms: TermsVersion
) -> None:
    # `BookingLoader` synthesises `booking-`-prefixed quotes; per CLAUDE.md they
    # must never leak into a public read, even at a quoted status.
    customer = _customer()
    synthetic_region = _property("synthetic-region")
    quote = _quote(
        person=customer,
        terms=terms,
        status=QuotationStatus.ACCEPTED.value,
        property_=synthetic_region,
        gbp=gbp,
    )
    quote.legacy_id = "booking-123"
    quote.save(update_fields=["legacy_id"])
    api_client.force_login(staff)

    row = _row_for(api_client, customer)
    assert "synthetic-region" not in row["quoted_region_slugs"]


@pytest.mark.django_db
def test_query_count_flat_with_region_aggregation(
    api_client: APIClient, staff: User, gbp: Currency, terms: TermsVersion
) -> None:
    api_client.force_login(staff)

    def _client_with_deals() -> Person:
        c = _customer()
        for slug in ("alpha", "beta"):
            prop = _property(f"{slug}-{c.pk}")
            _quote(
                person=c, terms=terms, status=QuotationStatus.SENT.value, property_=prop, gbp=gbp
            )
            _booking(person=c, property_=prop, gbp=gbp, terms=terms)
        return c

    _client_with_deals()
    with assert_max_queries(8) as one:
        assert api_client.get("/api/v1/clients").status_code == 200

    for _ in range(5):
        _client_with_deals()
    with assert_max_queries(8) as many:
        assert api_client.get("/api/v1/clients").status_code == 200

    assert len(one.captured_queries) == len(many.captured_queries)
