"""GAP-113: classify archive stays against the sheet-imported `PastStay` rows.

Read-only and order-independent: a sheet stay two archive stays both claim is
contested for both, never first-wins.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from accounts.enums import PersonKind, PersonStatus
from accounts.models import Person, PersonEmail
from data_migration.archive_stays import ArchiveStay, classify, notes_pending, parse_row
from pricing.models import Currency
from properties.factories import PropertyFactory
from properties.models import Property
from reservations.models import PastStay

pytestmark = pytest.mark.django_db

_SHEET_SEQ = iter(range(10_000))


@pytest.fixture
def villa() -> Property:
    return cast(Property, PropertyFactory(legacy_id="42"))


@pytest.fixture
def other_villa() -> Property:
    return cast(Property, PropertyFactory(legacy_id="43"))


@pytest.fixture
def gbp() -> Currency:
    return Currency.objects.create(code="GBP", name="Pound sterling", legacy_id="1")


def _person(first: str = "Tom", last: str = "Coopersmith", email: str = "", **kw: Any) -> Person:
    kw.setdefault("kind", PersonKind.CUSTOMER)
    person = Person.objects.create(first_name=first, last_name=last, **kw)
    if email:
        PersonEmail.objects.create(contact=person, email=email, is_primary=True)
    return person


def _sheet_stay(person: Person, **kw: Any) -> PastStay:
    kw.setdefault("villa_name", "Villa Yeraki")
    kw.setdefault("year", 2025)
    kw.setdefault("legacy_id", f"sheet-stay-{next(_SHEET_SEQ):016d}")
    return PastStay.objects.create(person=person, **kw)


def _stay(**overrides: Any) -> ArchiveStay:
    row: dict[str, Any] = {
        "Id": 100,
        "FromDate": datetime(2025, 8, 3),
        "ToDate": datetime(2025, 8, 10),
        "Amount": Decimal("4250"),
        "CurrencyId": 1,
        "VillaId": 42,
        "VillaName": "Villa Yeraki",
        "Notes": "BN1063",
        "FirstName": "Tom",
        "LastName": "Coopersmith",
        "Email": "tom@example.com",
    }
    row.update(overrides)
    return parse_row(row)


def _one(stay: ArchiveStay) -> tuple[str, PastStay | None]:
    [result] = classify([stay])
    return result.category, result.target


def test_an_already_created_archive_stay_exists() -> None:
    created = _sheet_stay(_person(), legacy_id="archive-stay-100")

    assert _one(_stay()) == ("exists", created)


def test_a_unique_same_year_booking_number_enriches(villa: Property) -> None:
    target = _sheet_stay(_person("Someone", "Else"), booking_number="BN1063", property=villa)

    [result] = classify([_stay()])

    assert (result.category, result.target) == ("enrich", target)
    assert result.property_differs is False


def test_booking_number_match_ignores_names_and_flags_a_different_villa(
    other_villa: Property,
) -> None:
    target = _sheet_stay(
        _person("Someone", "Else"), booking_number="BN1063 (422)", property=other_villa
    )

    [result] = classify([_stay()])

    assert (result.category, result.target) == ("enrich", target)
    assert result.property_differs is True


def test_the_booking_number_suffix_is_a_different_booking() -> None:
    plain = _sheet_stay(_person(), booking_number="BN1067")
    suffixed = _sheet_stay(_person("Ann", "Other"), booking_number="BN1067a")

    assert _one(_stay(Notes="BN1067a")) == ("enrich", suffixed)
    assert _one(_stay(Notes="BN1067")) == ("enrich", plain)


def test_two_same_year_booking_number_hits_are_ambiguous() -> None:
    _sheet_stay(_person(), booking_number="BN1063")
    _sheet_stay(_person("Ann", "Other"), booking_number="BN1063")

    assert _one(_stay()) == ("ambiguous", None)


def test_a_booking_number_only_in_another_year_is_a_conflict() -> None:
    _sheet_stay(_person(), booking_number="BN1063", year=2019)

    assert _one(_stay()) == ("bn_year_conflict", None)


def test_only_sheet_stays_are_candidates() -> None:
    _sheet_stay(_person(), booking_number="BN1063", legacy_id="archive-stay-7")

    assert _one(_stay())[0] == "create"


def test_the_email_tier_matches_the_single_customer_holding_the_address() -> None:
    # No BN on the archive row; the holder's name differs (a typo) — the address
    # alone identifies them.
    holder = _person("Tom", "Coppersmith", email="tom@example.com")
    target = _sheet_stay(holder)

    assert _one(_stay(Notes="")) == ("enrich", target)


def test_the_email_tier_ignores_a_shared_address() -> None:
    holder = _person("Tom", "Other", email="tom@example.com")
    _person("Tina", "Other", email="tom@example.com")
    _sheet_stay(holder)

    assert _one(_stay(Notes=""))[0] == "create"


def test_the_email_tier_needs_an_active_customer() -> None:
    _sheet_stay(_person("Tom", "Other", email="tom@example.com", status=PersonStatus.INACTIVE))
    _sheet_stay(_person("Tim", "Owner", email="tim@example.com", kind=PersonKind.CONTACT))

    assert _one(_stay(Notes=""))[0] == "create"
    assert _one(_stay(Notes="", Email="tim@example.com"))[0] == "create"


def test_the_email_tier_picks_the_stay_at_this_villa(
    villa: Property, other_villa: Property
) -> None:
    holder = _person(email="tom@example.com")
    _sheet_stay(holder, property=other_villa)
    here = _sheet_stay(holder, property=villa)

    assert _one(_stay(Notes="")) == ("enrich", here)


def test_the_name_tier_needs_first_and_last_names_to_agree() -> None:
    target = _sheet_stay(_person("Tom", "Coopersmith"))
    _sheet_stay(_person("Ann", "Davies"))

    assert _one(_stay(Notes="", Email="")) == ("enrich", target)
    assert _one(_stay(Notes="", Email="", FirstName="Bob", LastName="Davies"))[0] == "create"


def test_the_name_tier_rejects_a_stay_at_another_villa(other_villa: Property) -> None:
    _sheet_stay(_person(), property=other_villa)

    assert _one(_stay(Notes="", Email="")) == ("weak_conflict", None)


def test_the_name_tier_is_ambiguous_with_two_namesake_stays() -> None:
    _sheet_stay(_person())
    _sheet_stay(_person())

    assert _one(_stay(Notes="", Email="")) == ("ambiguous", None)


def test_nothing_matching_is_a_create_carrying_the_email_holder() -> None:
    holder = _person(email="tom@example.com")
    _sheet_stay(holder, year=2019)

    [result] = classify([_stay(Notes="")])

    assert result.category == "create"
    assert result.email_person == holder


def test_a_target_already_carrying_these_facts_exists(gbp: Currency) -> None:
    target = _sheet_stay(
        _person(),
        booking_number="BN1063",
        date_from=date(2025, 8, 3),
        date_to=date(2025, 8, 10),
        amount=Decimal("4250.00"),
        currency=gbp,
    )

    assert _one(_stay()) == ("exists", target)


def test_a_target_carrying_different_facts_is_taken() -> None:
    _sheet_stay(
        _person(), booking_number="BN1063", date_from=date(2025, 7, 1), date_to=date(2025, 7, 8)
    )

    assert _one(_stay()) == ("target_taken", None)


def test_archive_notes_still_to_append_keep_a_filled_target_pending(gbp: Currency) -> None:
    target = _sheet_stay(
        _person(),
        booking_number="BN1063",
        date_from=date(2025, 8, 3),
        date_to=date(2025, 8, 10),
        amount=Decimal("4250.00"),
        currency=gbp,
    )

    assert _one(_stay(Notes="BN1063\nPaid in full")) == ("enrich", target)
    target.notes = "Paid in full"
    target.save()
    assert _one(_stay(Notes="BN1063\nPaid in full")) == ("exists", target)


def test_two_archive_stays_claiming_one_target_are_both_contested() -> None:
    _sheet_stay(_person(), booking_number="BN1063")
    first = _stay(Id=1)
    second = replace(_stay(Id=2), date_from=date(2025, 9, 1), date_to=date(2025, 9, 8))

    forward = [(r.stay.legacy_id, r.category) for r in classify([first, second])]
    backward = [(r.stay.legacy_id, r.category) for r in classify([second, first])]

    assert sorted(forward) == sorted(backward) == [(1, "target_contested"), (2, "target_contested")]


def test_the_weak_tiers_skip_a_sheet_stay_with_another_booking_number() -> None:
    # Gibbens BN1005a has no sheet stay of its own; the holder's BN1005 is
    # another booking, not this one.
    holder = _person(email="tom@example.com")
    _sheet_stay(holder, booking_number="BN1005")
    unnumbered = _sheet_stay(_person("Ann", "Other"))

    assert _one(_stay(Notes="BN1005a"))[0] == "create"
    assert _one(_stay(Notes="BN1005a", FirstName="Ann", LastName="Other", Email=""))[1] == (
        unnumbered
    )


def test_notes_count_as_appended_only_as_whole_lines() -> None:
    target = _sheet_stay(_person(), booking_number="BN1063", notes="Paid deposit by card")

    assert notes_pending(_stay(Notes="BN1063 Paid"), target) is True
    target.notes = "Paid deposit by card\nPaid"
    assert notes_pending(_stay(Notes="BN1063 Paid"), target) is False


def test_the_email_holder_is_not_name_checked() -> None:
    # Michael / Mike Hobbs: a nickname is the same guest.
    holder = _person("Mike", "Hobbs", email="tom@example.com")

    [result] = classify([_stay(Notes="", FirstName="Michael", LastName="Hobbs")])

    assert (result.category, result.email_person) == ("create", holder)
