"""RatePlanAdmin.carry_forward_next_year targets the year after the regime's
latest period (GAP-110: the plan envelope is gone; periods date the regime)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import RequestFactory

from pricing.admin import RatePlanAdmin
from pricing.models import Currency, RateBand, RatePeriod, RatePlan
from properties.models import Property


def _request() -> object:
    request = RequestFactory().post("/admin/pricing/rateplan/")
    request._messages = CookieStorage(request)  # type: ignore[attr-defined]
    return request


@pytest.mark.django_db
def test_action_carries_the_year_after_the_latest_period(
    property_: Property, gbp: Currency
) -> None:
    plan = RatePlan.objects.create(property=property_, name="GBP rates", currency=gbp)
    for year in (2026, 2027):
        period = RatePeriod.objects.create(
            plan=plan, name=f"Summer {year}", date_from=date(year, 6, 1), date_to=date(year, 8, 31)
        )
        RateBand.objects.create(period=period, min_party=1, max_party=8, nightly=Decimal("200"))

    RatePlanAdmin(RatePlan, AdminSite()).carry_forward_next_year(
        _request(),  # type: ignore[arg-type]
        RatePlan.objects.filter(pk=plan.pk),
    )

    assert plan.periods.filter(date_from__year=2028).exists()
    assert not plan.periods.filter(date_from__year=2029).exists()


@pytest.mark.django_db
def test_action_ignores_withdrawn_periods_when_picking_the_year(
    property_: Property, gbp: Currency
) -> None:
    """The year rule is the service's (`next_target_year`): a withdrawn 2029
    period must not push the target to 2030 and leave 2029 unpriced."""
    plan = RatePlan.objects.create(property=property_, name="GBP rates", currency=gbp)
    period = RatePeriod.objects.create(
        plan=plan, name="Summer 2027", date_from=date(2027, 6, 1), date_to=date(2027, 8, 31)
    )
    RateBand.objects.create(period=period, min_party=1, max_party=8, nightly=Decimal("200"))
    RatePeriod.objects.create(
        plan=plan,
        name="Withdrawn 2029",
        date_from=date(2029, 6, 1),
        date_to=date(2029, 8, 31),
        is_active=False,
    )

    RatePlanAdmin(RatePlan, AdminSite()).carry_forward_next_year(
        _request(),  # type: ignore[arg-type]
        RatePlan.objects.filter(pk=plan.pk),
    )

    assert plan.periods.filter(date_from__year=2028, is_active=True).exists()
    assert not plan.periods.filter(date_from__year=2030).exists()


@pytest.mark.django_db
def test_action_warns_on_a_periodless_plan(property_: Property, gbp: Currency) -> None:
    plan = RatePlan.objects.create(property=property_, name="Empty", currency=gbp)
    request = _request()
    RatePlanAdmin(RatePlan, AdminSite()).carry_forward_next_year(
        request,  # type: ignore[arg-type]
        RatePlan.objects.filter(pk=plan.pk),
    )
    [message] = list(request._messages)  # type: ignore[attr-defined]
    assert "no periods" in str(message).lower()
    assert not plan.periods.exists()
