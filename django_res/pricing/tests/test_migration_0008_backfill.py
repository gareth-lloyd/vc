"""GAP-110 U1: the `pricing/0008` backfill stamps `RatePeriod.property` /
`.currency` from the owning plan.

Run against the *real* models (the historical ones share the columns): a
period whose stamps disagree with its plan — only reachable by a raw
`.update()`, since `save()` re-derives them — is corrected by the callable.
"""

from __future__ import annotations

from datetime import date
from importlib import import_module
from typing import cast

import pytest
from django.apps import apps

from pricing.factories import RatePlanFactory
from pricing.models import RatePeriod, RatePlan

_backfill = import_module("pricing.migrations.0008_rateperiod_property_currency").backfill_regime


@pytest.mark.django_db
def test_backfill_stamps_property_and_currency_from_plan(plan: RatePlan) -> None:
    period = RatePeriod.objects.create(
        plan=plan, name="June", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
    )
    other = cast(RatePlan, RatePlanFactory())
    # Bypass `save()` to plant stale stamps (the pre-0008 shape, modulo NULL).
    RatePeriod.objects.filter(pk=period.pk).update(property=other.property, currency=other.currency)

    _backfill(apps, None)

    period.refresh_from_db()
    assert period.property_id == plan.property_id
    assert period.currency_id == plan.currency_id
