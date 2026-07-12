"""Tests for `pricing.models.rate` invariants (GAP-056 period-native).

Uses the factories directly rather than the shared `plan`/`period` fixtures so
the constraint tests read as self-contained statements of each invariant.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import pytest
from django.db import IntegrityError, transaction

from pricing.factories import RatePeriodFactory, RatePlanFactory
from pricing.models import RateBand, RatePeriod, RatePlan


def _period(**kwargs: object) -> RatePeriod:
    kwargs.setdefault("date_from", date(2026, 6, 1))
    kwargs.setdefault("date_to", date(2026, 6, 30))
    return cast(RatePeriod, RatePeriodFactory(**kwargs))


# --- RateBand (party band) constraints ------------------------------------


@pytest.mark.django_db
def test_raterule_requires_a_period() -> None:
    """`period` is non-null — a band with no date-axis parent is rejected."""
    with pytest.raises(IntegrityError), transaction.atomic():
        RateBand.objects.create(min_party=1, max_party=4, nightly=Decimal("100"))


@pytest.mark.django_db
def test_raterule_min_party_must_be_lte_max_party() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        RateBand.objects.create(period=_period(), min_party=5, max_party=2, nightly=Decimal("100"))


@pytest.mark.django_db
def test_raterule_requires_nightly_or_weekly_or_poa() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        RateBand.objects.create(period=_period(), min_party=1, max_party=4)


@pytest.mark.django_db
def test_raterule_poa_allowed_without_prices() -> None:
    rr = RateBand.objects.create(period=_period(), min_party=1, max_party=4, is_poa=True)
    assert rr.pk is not None


@pytest.mark.django_db
def test_raterule_poa_cannot_coexist_with_nightly() -> None:
    """`is_poa=True` plus a numeric price are contradictory signals."""
    with pytest.raises(IntegrityError), transaction.atomic():
        RateBand.objects.create(
            period=_period(), min_party=1, max_party=4, is_poa=True, nightly=Decimal("50")
        )


@pytest.mark.django_db
def test_raterule_poa_cannot_coexist_with_weekly() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        RateBand.objects.create(
            period=_period(), min_party=1, max_party=4, is_poa=True, weekly=Decimal("350")
        )


@pytest.mark.django_db
def test_rateband_bands_no_overlap_same_period() -> None:
    """Two bands on one period with overlapping party ranges are forbidden
    (rateband_bands_no_overlap)."""
    period = _period()
    RateBand.objects.create(period=period, min_party=1, max_party=8, nightly=Decimal("100"))
    with pytest.raises(IntegrityError), transaction.atomic():
        RateBand.objects.create(period=period, min_party=2, max_party=6, nightly=Decimal("200"))


@pytest.mark.django_db
def test_rateband_bands_no_overlap_is_inclusive_on_party() -> None:
    """Party ranges are inclusive: a band starting on another's max overlaps."""
    period = _period()
    RateBand.objects.create(period=period, min_party=1, max_party=8, nightly=Decimal("100"))
    with pytest.raises(IntegrityError), transaction.atomic():
        RateBand.objects.create(period=period, min_party=8, max_party=12, nightly=Decimal("150"))


@pytest.mark.django_db
def test_raterule_disjoint_party_bands_may_share_period() -> None:
    """Occupancy bands: one period, disjoint party brackets — legal siblings."""
    period = _period()
    RateBand.objects.create(period=period, min_party=1, max_party=8, nightly=Decimal("100"))
    sibling = RateBand.objects.create(
        period=period, min_party=9, max_party=12, nightly=Decimal("250")
    )
    assert sibling.pk is not None


@pytest.mark.django_db
def test_raterule_same_party_allowed_across_periods() -> None:
    """The bands EXCLUDE is per-period: two periods may each carry a 1-8 band."""
    plan = RatePlanFactory()
    early = _period(plan=plan, date_from=date(2026, 6, 1), date_to=date(2026, 6, 14))
    late = _period(plan=plan, date_from=date(2026, 6, 15), date_to=date(2026, 6, 30))
    RateBand.objects.create(period=early, min_party=1, max_party=8, nightly=Decimal("100"))
    other = RateBand.objects.create(period=late, min_party=1, max_party=8, nightly=Decimal("150"))
    assert other.pk is not None


def test_ratecard_is_gone() -> None:
    """GAP-056 contract: the RateCard model no longer exists on the pricing app."""
    import pricing.models as pricing_models

    assert not hasattr(pricing_models, "RateCard")


def test_rateperiod_exported_from_models() -> None:
    """RatePeriod is part of the public pricing model surface."""
    assert RatePeriod.__name__ == "RatePeriod"
    assert RatePlan.__name__ == "RatePlan"
