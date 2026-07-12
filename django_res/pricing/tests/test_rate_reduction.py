"""RateBand reductions (Q-018): base price + separate reduction.

Mid-season rate cuts keep the *base* ``nightly``/``weekly`` and record the
reduction alongside — either ``reduction_percent`` (applies to both prices) or
explicit ``reduced_nightly``/``reduced_weekly`` new amounts. The effective
(quoted) price is always derived, never stored, so carry-over/projection copy
the base by construction.

Legal states pinned here:

* no reduction — all reduction fields NULL,
* percent — ``0 < reduction_percent < 100``, fixed amounts NULL,
* fixed — each reduced amount strictly below its (non-NULL) base,
* POA bands can carry no reduction of either kind.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError

from core.audit import get_spec
from pricing.models import RateBand, RatePeriod

pytestmark = pytest.mark.django_db


def make_band(period: RatePeriod, **overrides: object) -> RateBand:
    kwargs: dict[str, object] = {
        "period": period,
        "min_party": 1,
        "max_party": 8,
        "nightly": Decimal("200.00"),
    }
    kwargs.update(overrides)
    return RateBand.objects.create(**kwargs)


# --- effective prices ---------------------------------------------------------


def test_no_reduction_passthrough(period: RatePeriod) -> None:
    band = make_band(period, weekly=Decimal("1400.00"))
    assert band.effective_nightly == Decimal("200.00")
    assert band.effective_weekly == Decimal("1400.00")
    assert band.has_reduction is False


def test_percent_reduction_applies_to_both_prices(period: RatePeriod) -> None:
    band = make_band(
        period,
        weekly=Decimal("1400.00"),
        reduction_percent=Decimal("25.00"),
    )
    assert band.effective_nightly == Decimal("150.00")
    assert band.effective_weekly == Decimal("1050.00")
    assert band.has_reduction is True


def test_percent_reduction_quantizes_half_even(period: RatePeriod) -> None:
    """Half-cent results round like the engine: ROUND_HALF_EVEN to 0.01.

    10% off 333.35 = 300.015 -> 300.02 (ties to even last digit).
    """
    band = make_band(
        period,
        nightly=Decimal("333.35"),
        reduction_percent=Decimal("10.00"),
    )
    assert band.effective_nightly == Decimal("300.02")


def test_fixed_reduction_returns_new_amounts(period: RatePeriod) -> None:
    band = make_band(
        period,
        weekly=Decimal("1400.00"),
        reduced_nightly=Decimal("170.00"),
        reduced_weekly=Decimal("1190.00"),
    )
    assert band.effective_nightly == Decimal("170.00")
    assert band.effective_weekly == Decimal("1190.00")
    assert band.has_reduction is True


def test_weekly_only_band_percent(period: RatePeriod) -> None:
    band = make_band(
        period,
        nightly=None,
        weekly=Decimal("1400.00"),
        reduction_percent=Decimal("10.00"),
    )
    assert band.effective_nightly is None
    assert band.effective_weekly == Decimal("1260.00")


def test_effective_none_when_base_none(period: RatePeriod) -> None:
    """A missing base price stays missing — the reduction never invents one."""
    band = make_band(period, reduced_nightly=Decimal("170.00"))
    assert band.effective_weekly is None


# --- DB constraints -----------------------------------------------------------


def test_percent_at_or_above_100_rejected(period: RatePeriod) -> None:
    with pytest.raises(IntegrityError):
        make_band(period, reduction_percent=Decimal("100.00"))


def test_percent_zero_or_below_rejected(period: RatePeriod) -> None:
    with pytest.raises(IntegrityError):
        make_band(period, reduction_percent=Decimal("0.00"))


def test_percent_and_fixed_together_rejected(period: RatePeriod) -> None:
    with pytest.raises(IntegrityError):
        make_band(
            period,
            reduction_percent=Decimal("10.00"),
            reduced_nightly=Decimal("170.00"),
        )


def test_reduced_nightly_not_below_base_rejected(period: RatePeriod) -> None:
    with pytest.raises(IntegrityError):
        make_band(period, reduced_nightly=Decimal("200.00"))


def test_reduced_weekly_without_base_rejected(period: RatePeriod) -> None:
    with pytest.raises(IntegrityError):
        make_band(period, reduced_weekly=Decimal("900.00"))  # weekly base is NULL


def test_reduced_nightly_zero_rejected(period: RatePeriod) -> None:
    """A free stay must not be storable via the fixed path when 100% is not via percent."""
    with pytest.raises(IntegrityError):
        make_band(period, reduced_nightly=Decimal("0.00"))


def test_reduced_nightly_negative_rejected(period: RatePeriod) -> None:
    with pytest.raises(IntegrityError):
        make_band(period, reduced_nightly=Decimal("-50.00"))


def test_poa_with_percent_reduction_rejected(period: RatePeriod) -> None:
    with pytest.raises(IntegrityError):
        make_band(
            period,
            nightly=None,
            is_poa=True,
            reduction_percent=Decimal("10.00"),
        )


# --- audit trail ---------------------------------------------------------------


def test_reduction_money_fields_are_audit_tracked() -> None:
    """Reductions are exactly the operator price edits that need a trail."""
    spec = get_spec(RateBand)
    assert spec is not None
    tracked = set(spec.fields)
    assert {
        "reduction_percent",
        "reduced_nightly",
        "reduced_weekly",
        "reduced_at",
    } <= tracked
