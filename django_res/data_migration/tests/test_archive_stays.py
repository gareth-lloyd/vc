"""GAP-113: `archive_stays` — legacy `VillaArchiveBookings` rows → dated stays.

Parse + group are pure (plain dict rows in, `ArchiveStay` out); classification
against the sheet-imported `PastStay` rows needs the DB.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest

from data_migration.archive_stays import (
    bn_token,
    group_rows,
    leading_bn_token,
)


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "Id": 100,
        "FromDate": datetime(2025, 8, 3),
        "ToDate": datetime(2025, 8, 10),
        "Amount": Decimal("4250.0000"),
        "CurrencyId": 1,
        "VillaId": 42,
        "VillaName": "Villa Yeraki",
        "Notes": "BN1063\nPaid in full",
        "Title": "Mr",
        "FirstName": "Tom",
        "LastName": "Coopersmith",
        "Email": "Tom@Example.com ",
        "CountryCode": "44",
        "MobileNo": "7700900123",
        "Town": "Bath",
        "Country": "United Kingdom",
        "Postcode": "BA1 1AA",
        "Addressline1": "1 High St",
        "Addressline2": "",
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("text", "token"),
    [
        ("BN1063", "1063"),
        ("bn1057 - Client came to us", "1057"),
        ("BN 1004a", "1004a"),
        ("BN1004B", "1004b"),
        ("BN0659", "659"),
        ("BN1006\nDeposit carried over from BN887", "1006"),
        ("Paid in full", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_bn_token_is_the_first_booking_number_with_its_suffix(text: str | None, token: str) -> None:
    assert bn_token(text) == token


@pytest.mark.parametrize(
    ("booking_number", "token"),
    [
        ("BN443 (422)", "443"),
        ("BN450 / 510", "450"),
        ("BN1067a", "1067a"),
        ("see BN12", ""),  # only a LEADING token counts on the sheet side
        ("", ""),
    ],
)
def test_leading_bn_token_reads_only_the_sheet_numbers_first_token(
    booking_number: str, token: str
) -> None:
    assert leading_bn_token(booking_number) == token


def test_a_row_becomes_a_stay_with_normalised_values() -> None:
    result = group_rows([_row()])

    assert result.errors == []
    [stay] = result.stays
    assert stay.legacy_id == 100
    assert stay.member_ids == (100,)
    assert (stay.date_from, stay.date_to, stay.year) == (date(2025, 8, 3), date(2025, 8, 10), 2025)
    assert stay.amount == Decimal("4250.00")
    assert stay.currency_legacy_id == "1"
    assert (stay.villa_legacy_id, stay.villa_name) == ("42", "Villa Yeraki")
    assert stay.bn == "1063"
    assert stay.booking_number == "BN1063"
    assert stay.notes == "Paid in full"
    assert stay.email == "tom@example.com"
    assert (stay.first_name, stay.last_name) == ("Tom", "Coopersmith")
    assert stay.dates_dropped is False
    assert stay.duplicate_conflict is False


def test_zero_currency_and_zero_amount_are_null() -> None:
    [stay] = group_rows([_row(CurrencyId=0, Amount=Decimal("0"))]).stays

    assert stay.currency_legacy_id is None
    assert stay.amount is None


def test_booking_number_keeps_the_suffix_upper_cased_prefix() -> None:
    [stay] = group_rows([_row(Notes="BN 1004a")]).stays

    assert stay.booking_number == "BN1004a"
    assert stay.notes == ""


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [
        (datetime(2025, 8, 10), datetime(2025, 8, 3)),  # reversed
        (datetime(2025, 8, 10), datetime(2025, 8, 10)),  # zero nights
        (datetime(2025, 1, 1), datetime(2025, 9, 13)),  # 255 nights
    ],
)
def test_implausible_dates_are_dropped_but_the_stay_lands(
    date_from: datetime, date_to: datetime
) -> None:
    [stay] = group_rows([_row(FromDate=date_from, ToDate=date_to)]).stays

    assert (stay.date_from, stay.date_to) == (None, None)
    assert stay.year == date_from.year
    assert stay.dates_dropped is True


def test_a_45_night_stay_keeps_its_dates() -> None:
    [stay] = group_rows([_row(FromDate=datetime(2025, 7, 1), ToDate=datetime(2025, 8, 15))]).stays

    assert stay.date_to == date(2025, 8, 15)
    assert stay.dates_dropped is False


def test_the_known_test_row_is_excluded() -> None:
    result = group_rows([_row(Id=297)])

    assert result.stays == []
    assert result.test_row_ids == [297]


def test_a_row_without_a_from_date_is_an_error() -> None:
    result = group_rows([_row(Id=5, FromDate=None)])

    assert result.stays == []
    assert result.errors == [(5, "missing FromDate")]


def test_re_saves_of_one_booking_number_merge_whatever_the_guest_details() -> None:
    # Coopersmith/Coppersmith BN1063: 14 re-saves, some without the e-mail.
    result = group_rows(
        [
            _row(Id=10, LastName="Coopersmith", Email="jrc@example.com"),
            _row(Id=20, LastName="Coppersmith", Email=""),
            _row(Id=30, LastName="Coppersmith", Email=""),
        ]
    )

    [stay] = result.stays
    assert stay.legacy_id == 30
    assert stay.member_ids == (10, 20, 30)
    assert stay.last_name == "Coppersmith"
    assert stay.email == "jrc@example.com"  # the latest non-empty
    assert stay.duplicate_conflict is False


def test_a_re_save_correcting_a_date_merges_and_is_flagged() -> None:
    # Buckhurst BN1099: To 25 Jul re-saved as To 26 Jul.
    [stay] = group_rows(
        [_row(Id=268, ToDate=datetime(2025, 8, 9)), _row(Id=280, ToDate=datetime(2025, 8, 10))]
    ).stays

    assert stay.member_ids == (268, 280)
    assert stay.date_to == date(2025, 8, 10)
    assert stay.duplicate_conflict is True


def test_a_re_save_correcting_a_keying_slip_merges() -> None:
    [stay] = group_rows(
        [
            _row(Id=10, ToDate=datetime(2025, 12, 1)),  # ~120 nights: dropped alone
            _row(Id=11),
        ]
    ).stays

    assert stay.member_ids == (10, 11)
    assert (stay.date_from, stay.date_to) == (date(2025, 8, 3), date(2025, 8, 10))


def test_a_numberless_row_joins_the_overlapping_numbered_stay_of_its_guest() -> None:
    # Law: Id 57 (no BN) re-keyed a day later as Id 94 (BN1026), same e-mail.
    # Johnson: Id 50 (no BN) and Id 102 (BN1017) under different e-mails.
    result = group_rows(
        [
            _row(Id=57, Notes="", FromDate=datetime(2025, 8, 4), ToDate=datetime(2025, 8, 11)),
            _row(Id=94, Notes="BN1026"),
            _row(Id=50, VillaId=26, Notes="", LastName="Johnson", Email="h@example.com"),
            _row(Id=102, VillaId=26, Notes="BN1017", LastName="Johnson", Email="l@example.com"),
        ]
    )

    assert [(s.member_ids, s.bn) for s in result.stays] == [((57, 94), "1026"), ((50, 102), "1017")]


def test_the_latest_non_empty_booking_number_survives_a_re_save_without_one() -> None:
    [stay] = group_rows([_row(Id=10, Notes="BN1083"), _row(Id=11, Notes="Paid")]).stays

    assert stay.bn == "1083"
    assert stay.notes == "Paid"


def test_different_booking_numbers_are_different_stays() -> None:
    # Gibbens BN1005 / BN1005a: consecutive weeks; and overlapping numbers too.
    result = group_rows(
        [
            _row(Id=1, Notes="BN1005", ToDate=datetime(2025, 8, 10)),
            _row(
                Id=2, Notes="BN1005a", FromDate=datetime(2025, 8, 10), ToDate=datetime(2025, 8, 17)
            ),
            _row(Id=3, Notes="BN1006", FromDate=datetime(2025, 8, 5)),
        ]
    )

    assert [s.member_ids for s in result.stays] == [(1,), (2,), (3,)]


def test_one_booking_number_at_another_villa_is_another_stay() -> None:
    result = group_rows([_row(Id=1), _row(Id=2, VillaId=43)])

    assert [s.member_ids for s in result.stays] == [(1,), (2,)]


def test_re_saves_disagreeing_on_money_are_flagged() -> None:
    [stay] = group_rows(
        [_row(Id=10, Amount=Decimal("100")), _row(Id=11, Amount=Decimal("200"))]
    ).stays

    assert stay.legacy_id == 11
    assert stay.amount == Decimal("200.00")
    assert stay.duplicate_conflict is True


def test_different_guests_on_the_same_villa_and_dates_stay_separate() -> None:
    # VillaId 9, 3-10 Aug 2026: Bonnetons and Mellor.
    result = group_rows(
        [
            _row(Id=59, Notes="", LastName="Bonnetons", Email="b@example.com"),
            _row(Id=272, Notes="", LastName="Mellor", Email="m@example.com"),
        ]
    )

    assert [s.legacy_id for s in result.stays] == [59, 272]


def test_numberless_rows_without_email_or_surname_never_merge() -> None:
    result = group_rows(
        [
            _row(Id=1, Notes="", Email="", LastName="", FirstName="A"),
            _row(Id=2, Notes="", Email="", LastName="", FirstName="B"),
        ]
    )

    assert [s.member_ids for s in result.stays] == [(1,), (2,)]


def test_without_an_email_the_surname_identifies_the_guest() -> None:
    result = group_rows(
        [
            _row(Id=1, Notes="", Email="", LastName="Smith"),
            _row(Id=2, Notes="", Email=None, LastName=" smith "),
            _row(Id=3, Notes="", Email="", LastName="Jones"),
        ]
    )

    assert [s.member_ids for s in result.stays] == [(1, 2), (3,)]
