"""Regression: PricingEngine must tolerate the current PropertyFinance shape.

`engine._compute_commission/_compute_tax` were written against a future
`effective_*(as_of=...)` contract, but the live finance model returns
no-arg dicts. A `Property` with a real `PropertyFinance` row (as the seeder
and production create) must still quote instead of raising TypeError.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import cast

import pytest

from pricing.factories import RateRuleFactory
from pricing.models import RateRule
from pricing.services import PricingEngine

pytestmark = pytest.mark.django_db


def test_quote_succeeds_when_property_has_finance() -> None:
    rule = cast(RateRule, RateRuleFactory())  # PropertyFactory attaches a PropertyFinance row
    plan = rule.period.plan
    start = date.today() + timedelta(days=30)

    quote = PricingEngine.quote(
        property=plan.property,
        date_from=start,
        date_to=start + timedelta(days=7),
        party=2,
        currency=plan.currency,
    )

    assert quote.total > 0
