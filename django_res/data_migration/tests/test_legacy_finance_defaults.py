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

from data_migration.loaders.finance import apply_legacy_finance_defaults

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
