"""GAP-113: `import_archive_stays` — enrich sheet stays, create the unmatched."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from typing import Any, cast

import pytest
from django.core.management import call_command

from accounts.enums import PersonKind, PersonStatus
from accounts.models import Person, PersonEmail, PersonPhone
from data_migration.management.commands import import_archive_stays
from data_migration.sheets.matching import person_legacy_id
from pricing.models import Currency
from properties.factories import PropertyFactory
from properties.models import Country, Property
from reservations.models import PastStay

pytestmark = pytest.mark.django_db


@pytest.fixture
def villa() -> Property:
    return cast(Property, PropertyFactory(legacy_id="42"))


@pytest.fixture
def eur() -> Currency:
    return Currency.objects.create(code="EUR", name="Euro", legacy_id="3")


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "Id": 100,
        "FromDate": datetime(2025, 8, 3),
        "ToDate": datetime(2025, 8, 10),
        "Amount": Decimal("4250"),
        "CurrencyId": 3,
        "VillaId": 42,
        "VillaName": "Villa Yeraki",
        "Notes": "BN1063",
        "Title": "Mr",
        "FirstName": "Tom",
        "LastName": "Coopersmith",
        "Email": "tom@example.com",
        "CountryCode": "44",
        "MobileNo": "07911123456",
        "Town": "Bath",
        "Country": "United Kingdom",
        "Postcode": "BA1 1AA",
        "Addressline1": "1 High St",
        "Addressline2": "Flat 2",
    }
    row.update(overrides)
    return row


def _run(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]], *args: str) -> str:
    monkeypatch.setattr(import_archive_stays, "fetch_archive_rows", lambda: rows)
    out = StringIO()
    call_command("import_archive_stays", *args, stdout=out)
    return out.getvalue()


def _customer(first: str = "Tom", last: str = "Coopersmith", **kw: Any) -> Person:
    kw.setdefault("kind", PersonKind.CUSTOMER)
    return Person.objects.create(first_name=first, last_name=last, **kw)


def _sheet_stay(person: Person, **kw: Any) -> PastStay:
    kw.setdefault("villa_name", "Yeraki")
    kw.setdefault("year", 2025)
    kw.setdefault("legacy_id", "sheet-stay-0000000000000001")
    return PastStay.objects.create(person=person, **kw)


def test_enrich_blank_fills_the_sheet_stay_and_appends_notes_once(
    monkeypatch: pytest.MonkeyPatch, villa: Property, eur: Currency
) -> None:
    person = _customer(notes="Loyal guest")
    target = _sheet_stay(person, booking_number="BN1063", notes="From the sheet")
    rows = [_row(Notes="BN1063 Paid by transfer")]

    out = _run(monkeypatch, rows)

    target.refresh_from_db()
    assert (target.date_from, target.date_to) == (date(2025, 8, 3), date(2025, 8, 10))
    assert (target.amount, target.currency) == (Decimal("4250.00"), eur)
    assert target.notes == "From the sheet\nPaid by transfer"
    assert target.property is None  # never blank-filled (decision 10, revised)
    assert target.villa_name == "Yeraki"
    person.refresh_from_db()
    assert person.notes == "Loyal guest"
    assert not person.phones.exists() and not person.emails.exists()
    assert "updated" in out and "past_stay" in out

    _run(monkeypatch, rows)
    target.refresh_from_db()
    assert target.notes == "From the sheet\nPaid by transfer"


def test_enrich_keeps_values_the_archive_does_not_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _sheet_stay(_customer(), booking_number="BN1063")

    _run(monkeypatch, [_row(Amount=Decimal("0"), CurrencyId=0, Notes="BN1063")])

    target.refresh_from_db()
    assert (target.amount, target.currency, target.notes) == (None, None, "")
    assert target.date_from == date(2025, 8, 3)


def test_create_attaches_to_the_email_holder_without_giving_a_legacy_contact_a_phone(
    monkeypatch: pytest.MonkeyPatch, villa: Property, eur: Currency
) -> None:
    holder = _customer("Tom", "Coppersmith", legacy_id="4711")
    PersonEmail.objects.create(contact=holder, email="tom@example.com", is_primary=True)

    _run(monkeypatch, [_row(Notes="BN1063")])

    stay = PastStay.objects.get(legacy_id="archive-stay-100")
    assert stay.person == holder
    assert Person.objects.count() == 1
    assert not holder.phones.exists()


def test_create_mints_a_person_with_address_and_phone(
    monkeypatch: pytest.MonkeyPatch, villa: Property, eur: Currency
) -> None:
    gb, _ = Country.objects.get_or_create(iso2="GB", defaults={"iso3": "GBR", "name": "UK"})

    _run(monkeypatch, [_row(Notes="BN1063a Balance due")])

    stay = PastStay.objects.select_related("person").get(legacy_id="archive-stay-100")
    assert stay.booking_number == "BN1063a"
    assert (stay.villa_name, stay.property, stay.year) == ("Villa Yeraki", villa, 2025)
    assert (stay.date_from, stay.date_to) == (date(2025, 8, 3), date(2025, 8, 10))
    assert (stay.amount, stay.currency, stay.notes) == (Decimal("4250.00"), eur, "Balance due")
    person = stay.person
    assert person.legacy_id == person_legacy_id("tom@example.com", "Tom", "Coopersmith")
    assert (person.title, person.address_line_1, person.address_line_2) == (
        "Mr",
        "1 High St",
        "Flat 2",
    )
    assert (person.town, person.post_code, person.country) == ("Bath", "BA1 1AA", gb)
    assert list(person.emails.values_list("email", flat=True)) == ["tom@example.com"]
    assert list(person.phones.values_list("number", flat=True)) == ["+447911123456"]


def test_an_ambiguous_person_is_rolled_back_and_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _customer()
    _customer()

    out = _run(monkeypatch, [_row(Email="", Notes="")])

    assert Person.objects.count() == 2
    assert not PastStay.objects.exists()
    assert "person_ambiguous" in out


def test_an_inactive_person_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _customer(
        legacy_id=person_legacy_id("tom@example.com", "Tom", "Coopersmith"),
        status=PersonStatus.INACTIVE,
    )

    out = _run(monkeypatch, [_row(Notes="")])

    assert not PastStay.objects.exists()
    assert "person_inactive" in out


def test_dropped_dates_land_without_dates_and_name_the_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = _run(monkeypatch, [_row(Id=28, ToDate=datetime(2026, 4, 15), CurrencyId=0)])

    stay = PastStay.objects.get(legacy_id="archive-stay-28")
    assert (stay.year, stay.date_from, stay.date_to) == (2025, None, None)
    assert "dates_dropped" in out and "28" in out


def test_a_bad_row_is_isolated_and_reported(monkeypatch: pytest.MonkeyPatch, eur: Currency) -> None:
    rows = [
        _row(Id=1, CurrencyId=99, Email="a@example.com", LastName="Able"),
        _row(Id=2, Email="b@example.com", LastName="Baker", VillaId=43),
    ]

    out = _run(monkeypatch, rows)

    assert list(PastStay.objects.values_list("legacy_id", flat=True)) == ["archive-stay-2"]
    assert not Person.objects.filter(last_name="Able").exists()
    assert "Errors (1)" in out and "unknown CurrencyId 99" in out


def test_skips_and_the_test_row_are_named(monkeypatch: pytest.MonkeyPatch) -> None:
    _sheet_stay(_customer(), booking_number="BN1063", year=2019)

    out = _run(monkeypatch, [_row(Id=57), _row(Id=297, Notes="")])

    assert not PastStay.objects.filter(legacy_id__startswith="archive-stay-").exists()
    assert "bn_year_conflict" in out and "57" in out
    assert "test_row" in out and "297" in out


def test_dry_run_writes_nothing(monkeypatch: pytest.MonkeyPatch, eur: Currency) -> None:
    out = _run(monkeypatch, [_row()], "--dry-run")

    assert not PastStay.objects.exists() and not Person.objects.exists()
    assert "[dry-run]" in out


def test_a_second_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, villa: Property, eur: Currency
) -> None:
    _sheet_stay(_customer(), booking_number="BN1063", notes="")
    rows = [
        _row(Id=1, Notes="BN1063 Paid"),
        _row(Id=2, Notes="BN2000", Email="ann@example.com", FirstName="Ann", LastName="Lee"),
    ]
    _run(monkeypatch, rows)
    counts = (Person.objects.count(), PersonPhone.objects.count(), PastStay.objects.count())
    stamps = list(PastStay.objects.order_by("pk").values_list("updated_at", flat=True))

    out = _run(monkeypatch, rows)

    assert (Person.objects.count(), PersonPhone.objects.count(), PastStay.objects.count()) == (
        counts
    )
    assert list(PastStay.objects.order_by("pk").values_list("updated_at", flat=True)) == stamps
    assert "created" not in out and "updated" not in out


def test_flags_are_named_whatever_the_stay_ends_as(monkeypatch: pytest.MonkeyPatch) -> None:
    # 290: dropped dates, nothing to fill (exists); 7/8: re-saves disagreeing
    # on money whose person is ambiguous (rolled back).
    _sheet_stay(
        _customer("Ann", "Lee"),
        legacy_id="sheet-stay-0000000000000290",
        booking_number="BN2900",
    )
    _customer()
    _customer()
    rows = [
        _row(
            Id=290,
            Notes="BN2900",
            ToDate=datetime(2026, 1, 1),
            Amount=0,
            CurrencyId=0,
            FirstName="Ann",
            LastName="Lee",
            Email="ann@example.com",
        ),
        _row(Id=7, Email="", Notes="", Amount=Decimal("100")),
        _row(Id=8, Email="", Notes="", Amount=Decimal("200")),
    ]

    out = _run(monkeypatch, rows)

    assert "dates_dropped       290" in out
    assert "duplicate_conflict  7/8" in out
    assert "person_ambiguous    7/8" in out


def test_an_unresolved_country_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _run(monkeypatch, [_row(Country="Untied Kingdom", CurrencyId=0)])

    assert PastStay.objects.get().person.country is None
    assert "country_unresolved" in out
