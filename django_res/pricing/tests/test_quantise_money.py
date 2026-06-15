"""Tests for `pricing.services.currency.quantise_money` (SMELL-003)."""

from __future__ import annotations

from decimal import Decimal

from pricing.models import Currency
from pricing.services.currency import quantise_money


def _ccy(code: str, dp: int) -> Currency:
    return Currency(code=code, name=code, decimal_places=dp)


def test_quantise_two_decimal_places() -> None:
    usd = _ccy("USD", 2)
    assert quantise_money(Decimal("100.004"), usd) == Decimal("100.00")
    assert quantise_money(Decimal("100.006"), usd) == Decimal("100.01")
    assert quantise_money(Decimal("100"), usd) == Decimal("100.00")


def test_quantise_zero_decimal_currency_strips_minor_units() -> None:
    jpy = _ccy("JPY", 0)
    assert quantise_money(Decimal("100.49"), jpy) == Decimal("100")
    assert quantise_money(Decimal("100.51"), jpy) == Decimal("101")
    # HALF_EVEN: 100.50 -> 100 (0 is even)
    assert quantise_money(Decimal("100.50"), jpy) == Decimal("100")


def test_quantise_three_decimal_currency() -> None:
    bhd = _ccy("BHD", 3)
    assert quantise_money(Decimal("1.2345"), bhd) == Decimal("1.234")


def test_quantise_uses_bankers_rounding_half_even() -> None:
    usd = _ccy("USD", 2)
    # ROUND_HALF_EVEN: .005 -> .00 (2 is even), .015 -> .02 (2 is even)
    assert quantise_money(Decimal("0.125"), usd) == Decimal("0.12")
    assert quantise_money(Decimal("0.135"), usd) == Decimal("0.14")
