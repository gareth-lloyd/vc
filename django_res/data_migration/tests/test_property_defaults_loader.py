"""PropertyDefaultsLoader — legacy `VillaConfigPropertyDefault` → the
`PropertyDefaults` singleton (GAP-070 unit 6).

Transform-layer tests use hand-rolled dict fixtures (style reference:
`test_country_loader.py`); `@pytest.mark.django_db` only where the apply
path touches Postgres (currency FK + singleton write).
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from typing import Any

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.defaults import PropertyDefaultsLoader, _defaults_updates
from properties.enums import CommissionCalcType, DepositCalcType, PrefilledChangeOverDay
from properties.models.defaults import PropertyDefaults


def _legacy_row(**overrides: Any) -> dict[str, Any]:
    """A full VillaConfigPropertyDefault row (column names from the legacy
    entity class `ResSystem/Database/Data/VillaConfigPropertyDefault.cs`)."""
    row: dict[str, Any] = {
        "Id": 1,
        "AvailabilityStatus": 1,
        "IsBookingsRequirePreApproval": True,
        "PricesEnteredType": 1,
        "CurrencyId": None,
        "CommissionType": 1,
        "CommissionAmount": Decimal("20.00"),
        "CheckinTime": time(16, 0),
        "CheckOutTime": time(10, 0),
        "ChangeOverDay": 6,
        "MinimumNightsRental": Decimal("7.00"),
        "IsDepositRequired": True,
        "DepositType": 1,
        "DepositAmount": Decimal("30.00"),
        "IsInterimRequired": False,
        "InterimType": None,
        "InterimAmount": None,
        "DaysInterimDueBeforeArrival": 0,
        "DaysBalanceDueBeforeArrival": 60,
        "SecurityDepositRequired": True,
        "SecurityDepositAmountType": 2,
        "SecurityDepositAmount": Decimal("500.00"),
        "SecurityDepositCalculateFrom": 1,
        "SecurityDepositDaysDueBeforeArrival": 14,
        "SecurityDepositDaysDefundedAfterDeparture": 7,
    }
    row.update(overrides)
    return row


def test_maps_typo_refund_column() -> None:
    # The legacy DB column really is `...DefundedAfterDeparture` (see
    # design/departures.md) — it must land on the clean field name.
    updates = _defaults_updates(_legacy_row(SecurityDepositDaysDefundedAfterDeparture=9))
    assert updates["security_deposit_days_refunded_after_departure"] == 9


def test_maps_enums_and_decimal_nights() -> None:
    updates = _defaults_updates(_legacy_row())
    assert updates["commission_calculation_type"] == CommissionCalcType.PERCENT
    assert updates["deposit_calculation_type"] == DepositCalcType.PERCENT
    assert updates["changeover_day"] == PrefilledChangeOverDay.SAT
    # Legacy stores nights as decimal 7.00; the model field is an integer.
    assert updates["min_nights_rental"] == 7
    assert updates["check_in_time"] == time(16, 0)
    assert updates["bookings_require_pre_approval"] is True
    assert updates["security_deposit_amount"] == Decimal("500.00")


def test_changeover_day_is_the_code_domain() -> None:
    """The legacy column stores `ChangeOverDays.Code`, NOT the identity Id:
    -1 = Open/flexible, 0 = Sunday, 1 = Monday .. 6 = Saturday. -1 and 0 are
    real values (the prod dump's actual row is -1) — neither may be dropped
    as falsy/unmapped."""
    assert _defaults_updates(_legacy_row(ChangeOverDay=-1))["changeover_day"] == (
        PrefilledChangeOverDay.ANY
    )
    assert _defaults_updates(_legacy_row(ChangeOverDay=0))["changeover_day"] == (
        PrefilledChangeOverDay.SUN
    )
    assert _defaults_updates(_legacy_row(ChangeOverDay=1))["changeover_day"] == (
        PrefilledChangeOverDay.MON
    )


def test_none_columns_are_omitted_not_written() -> None:
    # A NULL legacy column must leave the current singleton value alone —
    # None never lands on the (non-nullable) PropertyDefaults fields.
    updates = _defaults_updates(
        _legacy_row(
            CommissionAmount=None,
            ChangeOverDay=None,
            CheckinTime=None,
            MinimumNightsRental=None,
        )
    )
    assert "commission_amount" not in updates
    assert "changeover_day" not in updates
    assert "check_in_time" not in updates
    assert "min_nights_rental" not in updates


def test_negative_numerics_are_dropped_as_junk() -> None:
    updates = _defaults_updates(
        _legacy_row(CommissionAmount=Decimal("-5"), DaysBalanceDueBeforeArrival=-1)
    )
    assert "commission_amount" not in updates
    assert "days_balance_due_before_arrival" not in updates


def test_unmapped_type_ids_are_omitted() -> None:
    updates = _defaults_updates(_legacy_row(CommissionType=99, ChangeOverDay=99))
    assert "commission_calculation_type" not in updates
    assert "changeover_day" not in updates


@pytest.mark.django_db
def test_apply_updates_singleton_with_currency_and_is_idempotent() -> None:
    from pricing.models.currency import Currency

    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    loader = PropertyDefaultsLoader()
    report = LoadReport(loader=loader.name)

    loader._apply(_legacy_row(CurrencyId=3), report)

    defaults = PropertyDefaults.get_solo()
    assert defaults.currency == eur
    assert defaults.min_nights_rental == 7
    assert defaults.commission_amount == Decimal("20.00")
    assert defaults.security_deposit_days_refunded_after_departure == 7
    assert report.updated == 1

    # Second pass: same values, still exactly one row, no error.
    loader._apply(_legacy_row(CurrencyId=3), report)
    assert PropertyDefaults.objects.count() == 1
    assert PropertyDefaults.get_solo().min_nights_rental == 7


@pytest.mark.django_db
def test_load_rows_skips_on_since_without_touching_the_singleton() -> None:
    # Delta runs must not clobber operator edits made through the new
    # PATCH /property-defaults endpoint during the cutover window.
    defaults = PropertyDefaults.get_solo()
    defaults.min_nights_rental = 3
    defaults.save()

    loader = PropertyDefaultsLoader(since="2026-07-01T00:00:00")
    report = LoadReport(loader=loader.name)
    loader._load_rows([_legacy_row()], report)

    assert PropertyDefaults.get_solo().min_nights_rental == 3
    assert report.skipped == 1 and report.updated == 0


@pytest.mark.django_db
def test_load_rows_empty_table_is_a_skip_not_a_crash() -> None:
    loader = PropertyDefaultsLoader()
    report = LoadReport(loader=loader.name)
    loader._load_rows([], report)
    # A skip, not an IndexError — and nothing written (the migration-seeded
    # singleton, when present, keeps its starter values).
    assert report.skipped == 1
    assert report.updated == 0 and not report.errors


@pytest.mark.django_db
def test_load_rows_isolates_a_junk_row_into_report_errors() -> None:
    # A junk legacy value must land in report.errors (like every BaseLoader
    # row) rather than raising out and aborting the whole loadlegacy run.
    loader = PropertyDefaultsLoader()
    report = LoadReport(loader=loader.name)
    junk = _legacy_row(CommissionAmount=Decimal("1e30"))  # overflows max_digits
    loader._load_rows([junk], report)
    assert report.updated == 0
    assert len(report.errors) == 1 and report.errors[0][0] == "1"


@pytest.mark.django_db
def test_apply_keeps_current_currency_when_legacy_id_unresolved() -> None:
    from pricing.models.currency import Currency

    gbp = Currency.objects.create(code="GBP", name="Pound", symbol="£", legacy_id="2")
    defaults = PropertyDefaults.get_solo()
    defaults.currency = gbp
    defaults.save()

    loader = PropertyDefaultsLoader()
    loader._apply(_legacy_row(CurrencyId=999), LoadReport(loader=loader.name))

    assert PropertyDefaults.get_solo().currency == gbp
