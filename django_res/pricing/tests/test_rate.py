"""Tests for `pricing.models.rate` invariants."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from pricing.models import RateCard, RateRule


@pytest.mark.django_db
def test_raterule_date_from_must_be_lt_date_to(card: RateCard) -> None:
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
def test_raterule_rejects_zero_length_range(card: RateCard) -> None:
    """A `[d, d)` rule covers zero nights — Booking/QuotationLine use `__lt`."""
    with pytest.raises(IntegrityError), transaction.atomic():
        RateRule.objects.create(
            card=card,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 1),
            min_party=1,
            max_party=4,
            nightly=Decimal("100"),
        )


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
