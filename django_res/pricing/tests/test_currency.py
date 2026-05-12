"""Tests for `pricing.models.currency`."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError

from pricing.models import Currency, FxRate


@pytest.mark.django_db
def test_fxrate_unique_per_base_quote_as_of() -> None:
    gbp = Currency.objects.create(code="GBP", name="Pound sterling")
    usd = Currency.objects.create(code="USD", name="US dollar")

    FxRate.objects.create(base=gbp, quote=usd, rate=Decimal("1.25"), as_of=date(2026, 1, 1))

    with pytest.raises(IntegrityError):
        FxRate.objects.create(base=gbp, quote=usd, rate=Decimal("1.30"), as_of=date(2026, 1, 1))


@pytest.mark.django_db
def test_fxrate_allows_distinct_dates() -> None:
    gbp = Currency.objects.create(code="GBP", name="Pound sterling")
    usd = Currency.objects.create(code="USD", name="US dollar")

    FxRate.objects.create(base=gbp, quote=usd, rate=Decimal("1.25"), as_of=date(2026, 1, 1))
    FxRate.objects.create(base=gbp, quote=usd, rate=Decimal("1.26"), as_of=date(2026, 1, 2))

    assert FxRate.objects.filter(base=gbp, quote=usd).count() == 2
