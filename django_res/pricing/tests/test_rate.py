"""Tests for `pricing.models.rate` invariants."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from pricing.models import RateCard, RatePeriod, RateRule


@pytest.mark.django_db
def test_raterule_date_from_must_be_lte_date_to(card: RateCard) -> None:
    """An inverted span (`date_from > date_to`) is still rejected."""
    with pytest.raises(IntegrityError), transaction.atomic():
        RateRule.objects.create(
            card=card,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 6, 1),
            min_party=1,
            max_party=4,
            nightly=Decimal("100"),
        )


@pytest.mark.django_db
def test_raterule_allows_single_day_range(card: RateCard) -> None:
    """GAP-056: dates are inclusive, so `date_from == date_to` is one valid night.

    (Was rejected under the old strict `<` CHECK; relaxed to `<=` so ragged
    segmentation can persist single-day fragments — see RatePeriod.)
    """
    rr = RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 1),
        min_party=1,
        max_party=4,
        nightly=Decimal("100"),
    )
    assert rr.pk is not None


@pytest.mark.django_db
def test_raterule_min_party_must_be_lte_max_party(card: RateCard) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        RateRule.objects.create(
            card=card,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            min_party=5,
            max_party=2,
            nightly=Decimal("100"),
        )


@pytest.mark.django_db
def test_raterule_requires_nightly_or_weekly_or_poa(card: RateCard) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        RateRule.objects.create(
            card=card,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            min_party=1,
            max_party=4,
            # no nightly, no weekly, is_poa default False
        )


@pytest.mark.django_db
def test_raterule_poa_allowed_without_prices(card: RateCard) -> None:
    rr = RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        min_party=1,
        max_party=4,
        is_poa=True,
    )
    assert rr.pk is not None


@pytest.mark.django_db
def test_raterule_poa_cannot_coexist_with_nightly(card: RateCard) -> None:
    """`is_poa=True` plus a numeric price are contradictory signals."""
    with pytest.raises(IntegrityError), transaction.atomic():
        RateRule.objects.create(
            card=card,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            min_party=1,
            max_party=4,
            is_poa=True,
            nightly=Decimal("50"),
        )


@pytest.mark.django_db
def test_raterule_poa_cannot_coexist_with_weekly(card: RateCard) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        RateRule.objects.create(
            card=card,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            min_party=1,
            max_party=4,
            is_poa=True,
            weekly=Decimal("350"),
        )


@pytest.mark.django_db
def test_raterule_no_overlap_same_card(card: RateCard) -> None:
    """Within-card overlap is forbidden unconditionally (raterule_no_overlap)."""
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        min_party=1,
        max_party=8,
        nightly=Decimal("100"),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        RateRule.objects.create(
            card=card,
            date_from=date(2026, 6, 15),
            date_to=date(2026, 7, 15),
            min_party=2,
            max_party=6,
            nightly=Decimal("200"),
        )


@pytest.mark.django_db
def test_raterule_no_overlap_is_inclusive_on_boundaries(card: RateCard) -> None:
    """Date ranges are inclusive: a rule starting on another's end date overlaps."""
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        min_party=1,
        max_party=8,
        nightly=Decimal("100"),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        RateRule.objects.create(
            card=card,
            date_from=date(2026, 6, 30),
            date_to=date(2026, 7, 31),
            min_party=1,
            max_party=8,
            nightly=Decimal("150"),
        )


@pytest.mark.django_db
def test_raterule_disjoint_party_bands_may_share_dates(card: RateCard) -> None:
    """Occupancy bands: same dates, disjoint party brackets — legal siblings."""
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        min_party=1,
        max_party=8,
        nightly=Decimal("100"),
    )
    sibling = RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        min_party=9,
        max_party=12,
        nightly=Decimal("250"),
    )
    assert sibling.pk is not None


@pytest.mark.django_db
def test_raterule_overlap_allowed_across_cards(card: RateCard) -> None:
    """Cross-card overlap is legal — precedence is resolved by card order."""
    other_card = RateCard.objects.create(plan=card.plan, name="Overlay", sort_order=1)
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        min_party=1,
        max_party=8,
        nightly=Decimal("100"),
    )
    overlapping = RateRule.objects.create(
        card=other_card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        min_party=1,
        max_party=8,
        nightly=Decimal("150"),
    )
    assert overlapping.pk is not None


@pytest.mark.django_db
def test_raterule_save_shim_populates_period(card: RateCard) -> None:
    """Transitional GAP-056 shim: a card-based create derives its RatePeriod."""
    rr = RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        min_party=1,
        max_party=8,
        nightly=Decimal("100"),
    )
    assert rr.period is not None
    assert rr.period.plan_id == card.plan_id
    assert (rr.period.date_from, rr.period.date_to) == (date(2026, 6, 1), date(2026, 6, 30))


@pytest.mark.django_db
def test_raterule_save_shim_reuses_period_for_sibling_band(card: RateCard) -> None:
    """Two disjoint-party bands on the same dates share one period [H2]."""
    band_a = RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        min_party=1,
        max_party=8,
        nightly=Decimal("100"),
    )
    band_b = RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        min_party=9,
        max_party=12,
        nightly=Decimal("250"),
    )
    assert band_a.period_id == band_b.period_id


@pytest.mark.django_db
def test_rateperiod_exported_from_models() -> None:
    """RatePeriod is part of the public pricing model surface."""
    assert RatePeriod.__name__ == "RatePeriod"
