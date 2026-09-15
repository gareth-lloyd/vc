"""BUG-028: legacy `IsDefault*` / `<= 0` substitution on VillaFinance rows.

Port of `PropertyService2.cs:169-238`: a flagged block is replaced wholesale
by the global `VillaConfigPropertyDefault` (CPD) row; an unflagged block has
each numeric `<= 0` field replaced individually. The legacy view model is
non-nullable, so a NULL numeric reads as 0 (substituted) and a NULL boolean
as False. Security-deposit "days due" come from the CPD's
`DaysBalanceDueBeforeArrival` in both branches (the CPD's own sec-dep days
column is dead in legacy).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from data_migration.loaders.finance import (
    RateRowFinance,
    apply_legacy_finance_defaults,
    apply_rate_row_finance,
    rate_row_finance_by_villa,
)

# The live CPD row on the 24-Apr-2025 dump (Id 1), plus interim values so the
# paysched block has something distinguishable to copy.
CPD: dict[str, Any] = {
    "Id": 1,
    "CommissionType": 10,
    "CommissionAmount": Decimal("20.00"),
    "IsDepositRequired": True,
    "DepositType": 10,
    "DepositAmount": Decimal("30.00"),
    "IsInterimRequired": False,
    "InterimType": 20,
    "InterimAmount": Decimal("5.00"),
    "DaysInterimDueBeforeArrival": 90,
    "DaysBalanceDueBeforeArrival": 56,
    "SecurityDepositRequired": True,
    "SecurityDepositAmountType": 10,
    "SecurityDepositAmount": Decimal("10.00"),
    "SecurityDepositDaysDueBeforeArrival": 0,
    "SecurityDepositDaysDefundedAfterDeparture": 14,
}

OWN: dict[str, Any] = {
    "Id": 10,
    "VillaId": 900,
    "IsDefaultCommission": False,
    "IsDefaultPaysched": False,
    "IsDefaultSecDep": False,
    "CommissionTypeId": 20,
    "CommissionAmount": Decimal("150"),
    "PaymentScheduleIsDepositRequired": True,
    "PaymentScheduleDepositTypeId": 20,
    "PaymentScheduleDepositAmount": Decimal("500"),
    "PaymentScheduleIsInterimRequired": True,
    "PaymentScheduleInterimTypeId": 10,
    "PaymentScheduleInterimAmount": Decimal("25"),
    "PaymentScheduleDaysInterimDueBeforeArrival": 120,
    "PaymentScheduleDaysBalanceDueBeforeArrival": 42,
    "SecurityDepositIsRequired": False,
    "SecurityDepositAmountTypeId": 20,
    "SecurityDepositAmount": Decimal("300"),
    "SecurityDepositDaysDueBeforeArrival": 7,
    "SecurityDepositDaysRefundedAfterDeparture": 21,
}


def _apply(**overrides: Any) -> dict[str, Any]:
    return apply_legacy_finance_defaults({**OWN, **overrides}, CPD)


def test_unflagged_positive_values_are_kept() -> None:
    assert _apply() == OWN


def test_input_row_is_not_mutated() -> None:
    row = {**OWN, "IsDefaultCommission": True}
    apply_legacy_finance_defaults(row, CPD)
    assert row["CommissionAmount"] == Decimal("150")


# --- commission -----------------------------------------------------------


def test_commission_flag_takes_amount_and_type_from_cpd() -> None:
    out = _apply(IsDefaultCommission=True)
    assert out["CommissionAmount"] == Decimal("20.00")
    assert out["CommissionTypeId"] == 10


@pytest.mark.parametrize("amount", [Decimal("0"), None, Decimal("-3")])
def test_unflagged_non_positive_commission_amount_takes_cpd_amount(
    amount: Decimal | None,
) -> None:
    out = _apply(CommissionAmount=amount)
    assert out["CommissionAmount"] == Decimal("20.00")
    assert out["CommissionTypeId"] == 20  # a positive own type is kept


@pytest.mark.parametrize("type_id", [0, None])
def test_unflagged_unset_commission_type_takes_cpd_type(type_id: int | None) -> None:
    # Deviation from legacy (which leaves 0): keeps amount and type paired.
    out = _apply(CommissionTypeId=type_id)
    assert out["CommissionTypeId"] == 10
    assert out["CommissionAmount"] == Decimal("150")


# --- payment schedule -----------------------------------------------------


def test_paysched_flag_copies_the_whole_block() -> None:
    out = _apply(IsDefaultPaysched=True)
    assert out["PaymentScheduleIsDepositRequired"] is True
    assert out["PaymentScheduleDepositTypeId"] == 10
    assert out["PaymentScheduleDepositAmount"] == Decimal("30.00")
    assert out["PaymentScheduleIsInterimRequired"] is False
    assert out["PaymentScheduleInterimTypeId"] == 20
    assert out["PaymentScheduleInterimAmount"] == Decimal("5.00")
    assert out["PaymentScheduleDaysInterimDueBeforeArrival"] == 90
    assert out["PaymentScheduleDaysBalanceDueBeforeArrival"] == 56


@pytest.mark.parametrize(
    ("column", "cpd_value"),
    [
        ("PaymentScheduleDepositTypeId", 10),
        ("PaymentScheduleDepositAmount", Decimal("30.00")),
        ("PaymentScheduleInterimTypeId", 20),
        ("PaymentScheduleInterimAmount", Decimal("5.00")),
        ("PaymentScheduleDaysInterimDueBeforeArrival", 90),
        ("PaymentScheduleDaysBalanceDueBeforeArrival", 56),
    ],
)
@pytest.mark.parametrize("own", [0, None, -1])
def test_unflagged_paysched_fills_each_non_positive_field(
    column: str, cpd_value: Any, own: Any
) -> None:
    out = _apply(**{column: own})
    assert out[column] == cpd_value
    # Only that field moved.
    assert {k for k in OWN if out[k] != OWN[k]} == {column}


def test_unflagged_paysched_booleans_are_never_substituted_and_null_is_false() -> None:
    out = _apply(PaymentScheduleIsDepositRequired=None, PaymentScheduleIsInterimRequired=False)
    assert out["PaymentScheduleIsDepositRequired"] is False
    assert out["PaymentScheduleIsInterimRequired"] is False


# --- security deposit -----------------------------------------------------


def test_secdep_flag_copies_the_block_with_days_from_balance_due() -> None:
    out = _apply(IsDefaultSecDep=True)
    assert out["SecurityDepositIsRequired"] is True
    assert out["SecurityDepositAmountTypeId"] == 10
    assert out["SecurityDepositAmount"] == Decimal("10.00")
    # Legacy reads DaysBalanceDueBeforeArrival here, not the CPD's own 0.
    assert out["SecurityDepositDaysDueBeforeArrival"] == 56
    assert out["SecurityDepositDaysRefundedAfterDeparture"] == 14


@pytest.mark.parametrize(
    ("column", "cpd_value"),
    [
        ("SecurityDepositAmountTypeId", 10),
        ("SecurityDepositAmount", Decimal("10.00")),
        ("SecurityDepositDaysDueBeforeArrival", 56),
        ("SecurityDepositDaysRefundedAfterDeparture", 14),
    ],
)
@pytest.mark.parametrize("own", [0, None])
def test_unflagged_secdep_fills_each_non_positive_field(
    column: str, cpd_value: Any, own: Any
) -> None:
    out = _apply(**{column: own})
    assert out[column] == cpd_value
    assert {k for k in OWN if out[k] != OWN[k]} == {column}


def test_unflagged_not_required_secdep_keeps_required_false() -> None:
    # 92 dump villas: not required, type 0, amount 0 — the <=0 rule fills
    # type and amount, but `required` is a boolean and stays False.
    out = _apply(
        SecurityDepositIsRequired=False, SecurityDepositAmountTypeId=0, SecurityDepositAmount=0
    )
    assert out["SecurityDepositIsRequired"] is False
    assert out["SecurityDepositAmountTypeId"] == 10
    assert out["SecurityDepositAmount"] == Decimal("10.00")


# --- flags ----------------------------------------------------------------


@pytest.mark.parametrize("flag", [True, 1, -1])
def test_any_truthy_flag_counts_as_set(flag: Any) -> None:
    # A historic seed script wrote -1; never compare flags with `== 1`.
    assert _apply(IsDefaultCommission=flag)["CommissionTypeId"] == 10


@pytest.mark.parametrize("flag", [False, 0, None])
def test_falsy_flag_is_unset(flag: Any) -> None:
    assert _apply(IsDefaultCommission=flag)["CommissionTypeId"] == 20


def test_missing_cpd_raises() -> None:
    with pytest.raises(RuntimeError):
        apply_legacy_finance_defaults(OWN, None)


# --- per-villa commission/tax from rate rows (D7) -------------------------


def _group(villa: int, n: int, **cols: Any) -> dict[str, Any]:
    base = {
        "VillaId": villa,
        "CommissionType": 10,
        "Commission": Decimal("15.00"),
        "TaxRate": None,
        "IsTaxExempt": False,
        "N": n,
    }
    return {**base, **cols}


def test_majority_commission_wins_by_row_count() -> None:
    out = rate_row_finance_by_villa(
        [
            _group(1, 5),
            _group(1, 2, CommissionType=20, Commission=Decimal("100.00")),
        ]
    )
    assert out["1"].commission == (10, Decimal("15.00"))
    assert out["1"].commission_mixed is True


def test_tie_breaks_on_lowest_type_then_amount() -> None:
    out = rate_row_finance_by_villa(
        [
            _group(1, 3, CommissionType=20, Commission=Decimal("50.00")),
            _group(1, 3, CommissionType=10, Commission=Decimal("18.00")),
            _group(1, 3, CommissionType=10, Commission=Decimal("12.00")),
        ]
    )
    assert out["1"].commission == (10, Decimal("12.00"))


def test_zero_or_untyped_commission_rows_do_not_vote() -> None:
    out = rate_row_finance_by_villa(
        [
            _group(1, 9, Commission=Decimal("0")),
            _group(1, 9, CommissionType=0),
            _group(1, 9, CommissionType=None, Commission=None),
        ]
    )
    assert out["1"].commission is None
    assert out["1"].commission_mixed is False


def test_single_value_villa_is_not_mixed_and_amounts_quantise() -> None:
    out = rate_row_finance_by_villa(
        [_group(2, 4, Commission=Decimal("15")), _group(2, 1, Commission=Decimal("15.00"))]
    )
    assert out["2"].commission == (10, Decimal("15.00"))
    assert out["2"].commission_mixed is False


def test_tax_majority_counts_rates_and_exemptions() -> None:
    out = rate_row_finance_by_villa(
        [
            _group(1, 4, TaxRate=13),
            _group(1, 1, TaxRate=24),
            _group(1, 9, TaxRate=0),  # no tax information: does not vote
            _group(2, 3, IsTaxExempt=True, TaxRate=13),
        ]
    )
    assert out["1"].tax == (Decimal("13"), False)
    assert out["1"].tax_mixed is True
    assert out["2"].tax == (Decimal("0"), True)


FINANCE_ROW: dict[str, Any] = {
    "IsDefaultCommission": False,
    "CommissionTypeId": 20,
    "CommissionAmount": Decimal("150"),
    "TaxExempt": False,
    "TaxPercentage": Decimal("10"),
}
MAJORITY = RateRowFinance(
    commission=(10, Decimal("15.00")),
    tax=(Decimal("13"), False),
    commission_mixed=False,
    tax_mixed=False,
)


def test_flagged_commission_takes_the_rate_row_majority_and_clears_the_flag() -> None:
    out = apply_rate_row_finance({**FINANCE_ROW, "IsDefaultCommission": True}, MAJORITY)
    assert (out["CommissionTypeId"], out["CommissionAmount"]) == (10, Decimal("15.00"))
    assert not out["IsDefaultCommission"]
    # ...so the CPD rule that runs next leaves it alone.
    resolved = apply_legacy_finance_defaults(out, CPD)
    assert resolved["CommissionAmount"] == Decimal("15.00")


def test_zero_commission_takes_the_majority() -> None:
    out = apply_rate_row_finance({**FINANCE_ROW, "CommissionAmount": Decimal("0")}, MAJORITY)
    assert out["CommissionAmount"] == Decimal("15.00")


def test_rate_row_majority_beats_own_explicit_commission_and_tax() -> None:
    # Legacy's quote reads a priced night's rate row before VillaFinance
    # (quote_price_calc-query.sql:96-146), so the majority wins outright.
    out = apply_rate_row_finance(FINANCE_ROW, MAJORITY)
    assert (out["CommissionTypeId"], out["CommissionAmount"]) == (10, Decimal("15.00"))
    assert (out["TaxPercentage"], out["TaxExempt"]) == (Decimal("13"), False)


@pytest.mark.parametrize("own_tax", [None, Decimal("0")])
def test_unset_tax_takes_the_majority(own_tax: Decimal | None) -> None:
    out = apply_rate_row_finance({**FINANCE_ROW, "TaxPercentage": own_tax}, MAJORITY)
    assert (out["TaxPercentage"], out["TaxExempt"]) == (Decimal("13"), False)


def test_exempt_villa_loses_its_exemption_to_a_taxed_majority() -> None:
    row = {**FINANCE_ROW, "TaxPercentage": None, "TaxExempt": True}
    out = apply_rate_row_finance(row, MAJORITY)
    assert (out["TaxPercentage"], out["TaxExempt"]) == (Decimal("13"), False)


def test_villa_without_a_commission_or_tax_majority_keeps_its_own() -> None:
    no_votes = RateRowFinance(commission=None, tax=None, commission_mixed=False, tax_mixed=False)
    assert apply_rate_row_finance(FINANCE_ROW, no_votes) == FINANCE_ROW


def test_no_rate_rows_changes_nothing() -> None:
    row = {**FINANCE_ROW, "IsDefaultCommission": True}
    assert apply_rate_row_finance(row, None) == row
