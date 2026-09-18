"""GAP-089: `PastStay` — the honest minimal record of a historic stay imported
from Nick's spreadsheets (villa + year + booking number). GAP-113 adds the
optional exact dates and recorded amount from legacy `VillaArchiveBookings`.

Surfaces on Customer-360 and the /bookings tab as "Imported bookings" (GAP-117)
and folds into the derived `is_repeat_customer` flag on both `/contacts/{id}`
and `/clients`.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import cast

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from accounts.factories import CustomerPersonFactory
from accounts.models import Person, User
from core.enums import StaffRole
from core.models import AuditLog
from core.tests import assert_max_queries
from pricing.models import Currency
from properties.models import Property
from reservations.enums import BookingStatus
from reservations.factories import TermsVersionFactory, make_occupying_booking
from reservations.models import PastStay, TermsVersion

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True, email="staff@example.com", password="x", role=StaffRole.RESERVATIONS
    )


@pytest.fixture
def person(db: None) -> Person:
    return cast(Person, CustomerPersonFactory())


def _stay(person: Person, **kwargs: object) -> PastStay:
    defaults: dict[str, object] = {"villa_name": "Villa Yeraki", "year": 2019}
    defaults.update(kwargs)
    if isinstance(defaults.get("date_from"), date) and "date_to" not in kwargs:
        defaults["date_to"] = cast(date, defaults["date_from"]) + timedelta(days=7)
    return PastStay.objects.create(person=person, **defaults)


def test_default_ordering_is_newest_year_first(person: Person) -> None:
    old = _stay(person, year=2017, booking_number="BN10")
    undated = _stay(person, year=None, booking_number="BN99")
    new = _stay(person, year=2023, booking_number="BN500")

    assert list(PastStay.objects.all()) == [new, old, undated]


def test_ordering_within_a_year_is_newest_dates_first_then_undated(person: Person) -> None:
    undated = _stay(person, year=2023, booking_number="BN1")
    early = _stay(
        person,
        year=2023,
        booking_number="BN9",
        date_from=date(2023, 5, 1),
        date_to=date(2023, 5, 8),
    )
    late = _stay(
        person,
        year=2023,
        booking_number="BN5",
        date_from=date(2023, 9, 1),
        date_to=date(2023, 9, 8),
    )

    assert list(PastStay.objects.all()) == [late, early, undated]


def test_dates_amount_and_currency_round_trip(person: Person, gbp: Currency) -> None:
    stay = _stay(
        person,
        date_from=date(2025, 8, 3),
        date_to=date(2025, 8, 10),
        amount=Decimal("4250.00"),
        currency=gbp,
    )

    stay.refresh_from_db()
    assert (stay.date_from, stay.date_to) == (date(2025, 8, 3), date(2025, 8, 10))
    assert stay.amount == Decimal("4250.00")
    assert stay.currency == gbp


def test_dates_amount_and_currency_default_to_null(person: Person) -> None:
    stay = _stay(person)

    stay.refresh_from_db()
    assert (stay.date_from, stay.date_to, stay.amount, stay.currency) == (None, None, None, None)


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [
        (date(2025, 8, 3), None),
        (None, date(2025, 8, 10)),
        (date(2025, 8, 10), date(2025, 8, 10)),
        (date(2025, 8, 10), date(2025, 8, 3)),
    ],
)
def test_dates_must_be_both_or_neither_and_ordered(
    person: Person, date_from: date | None, date_to: date | None
) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        _stay(person, date_from=date_from, date_to=date_to)


def test_date_and_amount_edits_are_audited(person: Person, gbp: Currency) -> None:
    stay = _stay(person)

    stay.date_from = date(2025, 8, 3)
    stay.date_to = date(2025, 8, 10)
    stay.amount = Decimal("100.00")
    stay.currency = gbp
    stay.save()

    ct = ContentType.objects.get_for_model(PastStay)
    diffs = [
        r.field_diffs for r in AuditLog.objects.filter(content_type=ct, object_id=str(stay.pk))
    ]
    changed = {key for diff in diffs for key in diff}
    assert {"date_from", "date_to", "amount", "currency_id"} <= changed


def test_contact_past_stays_lists_rows_with_optional_property(
    api_client: APIClient, staff: User, person: Person, property_: Property
) -> None:
    linked = _stay(
        person,
        booking_number="BN500",
        villa_name="Test Villa",
        property=property_,
        destination="Corfu",
        year=2023,
    )
    unlinked = _stay(person, booking_number="BN10", villa_name="Villa Unknown", year=2017)
    _stay(cast(Person, CustomerPersonFactory()), booking_number="BN1")  # someone else's
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/contacts/{person.pk}/past-stays")

    assert response.status_code == 200
    rows = response.json()["results"]
    assert [r["id"] for r in rows] == [linked.pk, unlinked.pk]
    assert rows[0] == {
        "id": linked.pk,
        "booking_number": "BN500",
        "villa_name": "Test Villa",
        "property": property_.pk,
        "property_name": "Test Villa",
        "destination": "Corfu",
        "year": 2023,
        "notes": "",
        "date_from": None,
        "date_to": None,
        "amount": None,
        "currency_code": None,
    }
    assert rows[1]["property"] is None
    assert rows[1]["property_name"] is None


def test_contact_past_stays_exposes_dates_and_recorded_amount(
    api_client: APIClient, staff: User, person: Person, gbp: Currency
) -> None:
    _stay(
        person,
        year=2025,
        date_from=date(2025, 8, 3),
        date_to=date(2025, 8, 10),
        amount=Decimal("4250.00"),
        currency=gbp,
    )
    _stay(person, year=2018, amount=Decimal("900.00"))  # amount recorded without a currency
    api_client.force_login(staff)

    rows = api_client.get(f"/api/v1/contacts/{person.pk}/past-stays").json()["results"]

    assert [(r["date_from"], r["date_to"], r["amount"], r["currency_code"]) for r in rows] == [
        ("2025-08-03", "2025-08-10", "4250.00", "GBP"),
        (None, None, "900.00", None),
    ]


def test_contact_past_stays_requires_staff(api_client: APIClient, person: Person) -> None:
    user = User.objects.create_user(is_staff=False, email="owner@example.com", password="x")
    api_client.force_login(user)

    assert api_client.get(f"/api/v1/contacts/{person.pk}/past-stays").status_code == 403


def test_contact_detail_counts_past_stays_as_repeat(
    api_client: APIClient, staff: User, person: Person
) -> None:
    _stay(person)
    _stay(person, year=2021)
    api_client.force_login(staff)

    body = api_client.get(f"/api/v1/contacts/{person.pk}").json()

    assert body["booking_count"] == 0
    assert body["past_stay_count"] == 2
    assert body["is_repeat_customer"] is True


def test_contact_list_past_stay_count_does_not_inflate_booking_count(
    api_client: APIClient, staff: User, person: Person
) -> None:
    # Two annotations over two reverse FKs must not cross-join into a product.
    _stay(person)
    _stay(person, year=2021)
    _stay(person, year=2022)
    api_client.force_login(staff)

    body = api_client.get("/api/v1/contacts").json()

    row = next(r for r in body["results"] if r["id"] == person.pk)
    assert body["count"] == 1
    assert row["past_stay_count"] == 3
    assert row["booking_count"] == 0


def test_clients_list_marks_past_stay_only_client_as_repeat(
    api_client: APIClient, staff: User, person: Person
) -> None:
    _stay(person)
    never = cast(Person, CustomerPersonFactory())
    api_client.force_login(staff)

    results = api_client.get("/api/v1/clients").json()["results"]
    repeat_ids = {r["id"] for r in api_client.get("/api/v1/clients?repeat=true").json()["results"]}

    row = next(r for r in results if r["id"] == person.pk)
    assert row["is_repeat_customer"] is True
    assert person.pk in repeat_ids
    assert never.pk not in repeat_ids


def test_contact_types_treats_a_past_stay_as_having_booked(
    api_client: APIClient, staff: User
) -> None:
    # A non-customer kind with only a sheet stay: `is_repeat_customer` and the
    # CUSTOMER type badge must agree (both derive from "has booked").
    contact = Person.objects.create(first_name="Old", last_name="Guest", kind="contact")
    _stay(contact)
    api_client.force_login(staff)

    body = api_client.get(f"/api/v1/contacts/{contact.pk}").json()

    assert body["is_repeat_customer"] is True
    assert "customer" in body["contact_types"]


def test_anonymize_blanks_past_stay_notes_but_keeps_the_stay(person: Person) -> None:
    stay = _stay(person, notes="CANCELLED\nYear as written: 1905")

    person.anonymize()

    stay.refresh_from_db()
    assert stay.person == person
    assert stay.villa_name == "Villa Yeraki"
    assert stay.notes == ""


def test_person_merge_moves_past_stays(person: Person) -> None:
    target = cast(Person, CustomerPersonFactory())
    stay = _stay(person)

    person.merge(target)

    stay.refresh_from_db()
    assert stay.person == target
    assert not Person.objects.filter(pk=person.pk).exists()


# ----------------------------------------------------------------------
# GAP-117: cross-client `GET /past-stays` — the "Imported bookings" tab on
# /bookings. Imported rows only: an app-created `Booking` never appears.
# ----------------------------------------------------------------------

PAST_STAYS_URL = "/api/v1/past-stays"


def test_past_stays_list_rejects_anonymous(api_client: APIClient) -> None:
    assert api_client.get(PAST_STAYS_URL).status_code == 403


def test_past_stays_list_requires_staff(api_client: APIClient) -> None:
    user = User.objects.create_user(is_staff=False, email="owner@example.com", password="x")
    api_client.force_login(user)

    assert api_client.get(PAST_STAYS_URL).status_code == 403


def test_past_stays_list_spans_clients_with_guest_fields(
    api_client: APIClient, staff: User, person: Person, property_: Property, gbp: Currency
) -> None:
    other = cast(Person, CustomerPersonFactory(first_name="Olga", last_name="Other"))
    mine = _stay(
        person,
        booking_number="BN500",
        villa_name="Test Villa",
        property=property_,
        destination="Corfu",
        year=2023,
        date_from=date(2023, 8, 3),
        amount=Decimal("4250.00"),
        currency=gbp,
    )
    theirs = _stay(other, booking_number="BN10", villa_name="Villa Unknown", year=2017)
    api_client.force_login(staff)

    response = api_client.get(PAST_STAYS_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert [r["id"] for r in body["results"]] == [mine.pk, theirs.pk]
    assert body["results"][0] == {
        "id": mine.pk,
        "booking_number": "BN500",
        "villa_name": "Test Villa",
        "property": property_.pk,
        "property_name": "Test Villa",
        "destination": "Corfu",
        "year": 2023,
        "notes": "",
        "date_from": "2023-08-03",
        "date_to": "2023-08-10",
        "amount": "4250.00",
        "currency_code": "GBP",
        "person": person.pk,
        "person_name": person.display_name,
    }
    assert body["results"][1]["person"] == other.pk
    assert body["results"][1]["person_name"] == "Olga Other"
    assert body["results"][1]["currency_code"] is None


def test_past_stays_list_null_person_name_when_name_blank(
    api_client: APIClient, staff: User
) -> None:
    nameless = Person.objects.create(first_name="", last_name="", kind="customer")
    _stay(nameless)
    api_client.force_login(staff)

    row = api_client.get(PAST_STAYS_URL).json()["results"][0]

    assert row["person"] == nameless.pk
    assert row["person_name"] is None


def test_past_stays_list_keeps_model_ordering_and_ignores_ordering_param(
    api_client: APIClient, staff: User, person: Person
) -> None:
    old = _stay(person, year=2017, notes="a")
    undated = _stay(person, year=None, notes="b")
    late = _stay(person, year=2023, date_from=date(2023, 9, 1), notes="c")
    early = _stay(person, year=2023, date_from=date(2023, 5, 1), notes="d")
    api_client.force_login(staff)

    expected = [late.pk, early.pk, old.pk, undated.pk]
    for url in (PAST_STAYS_URL, f"{PAST_STAYS_URL}?ordering=notes"):
        assert [r["id"] for r in api_client.get(url).json()["results"]] == expected


def test_past_stays_list_breaks_ordering_ties_by_pk(
    api_client: APIClient, staff: User, person: Person
) -> None:
    # Identical sort keys (sheet rows: same year, no dates, blank number) must
    # still page deterministically.
    tied = [_stay(person, year=2019, booking_number="").pk for _ in range(3)]
    api_client.force_login(staff)

    assert [r["id"] for r in api_client.get(PAST_STAYS_URL).json()["results"]] == tied


@pytest.mark.parametrize("term", ["Zanzibar", "Villa Kamara", "BN777", "Grand Kamara"])
def test_past_stays_list_search(
    api_client: APIClient, staff: User, person: Person, property_: Property, term: str
) -> None:
    property_.display_name = "Grand Kamara Estate"
    property_.save()
    guest = cast(Person, CustomerPersonFactory(first_name="Ann", last_name="Zanzibar"))
    hits = {
        "Zanzibar": lambda: _stay(guest),
        "Villa Kamara": lambda: _stay(person, villa_name="Villa Kamara"),
        "BN777": lambda: _stay(person, booking_number="BN777"),
        "Grand Kamara": lambda: _stay(person, villa_name="Sheet name", property=property_),
    }
    hit = hits[term]()
    decoy = _stay(person, villa_name="Villa Decoy", booking_number="BN1")
    api_client.force_login(staff)

    ids = [r["id"] for r in api_client.get(PAST_STAYS_URL, {"search": term}).json()["results"]]

    assert hit.pk in ids
    assert decoy.pk not in ids


def test_past_stays_list_excludes_app_bookings(
    api_client: APIClient, staff: User, person: Person, property_: Property, gbp: Currency
) -> None:
    booking = make_occupying_booking(
        property=property_,
        person=person,
        currency=gbp,
        terms=cast(TermsVersion, TermsVersionFactory()),
        date_from=date(2024, 6, 1),
        date_to=date(2024, 6, 8),
    )
    booking.status = BookingStatus.CHECKED_OUT
    booking.save()
    stay = _stay(person)
    api_client.force_login(staff)

    body = api_client.get(PAST_STAYS_URL).json()

    assert body["count"] == 1
    assert [r["id"] for r in body["results"]] == [stay.pk]


# Session + user + COUNT + page SELECT (person/property/currency joined).
QUERY_PIN = 4


def test_past_stays_list_query_count_is_flat(
    api_client: APIClient, staff: User, property_: Property, gbp: Currency
) -> None:
    def seed(n: int) -> None:
        for i in range(n):
            guest = cast(Person, CustomerPersonFactory())
            _stay(guest, property=property_, amount=Decimal("1.00"), currency=gbp, year=2000 + i)

    api_client.force_login(staff)
    seed(2)
    with assert_max_queries(QUERY_PIN):
        assert api_client.get(PAST_STAYS_URL).status_code == 200
    seed(6)
    with assert_max_queries(QUERY_PIN):
        assert api_client.get(PAST_STAYS_URL).json()["count"] == 8
