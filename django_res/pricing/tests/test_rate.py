"""Tests for `pricing.models.rate` invariants."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from pricing.models import RateCard, RateRule


@pytest.mark.django_db
def test_raterule_date_from_must_be_lte_date_to(card: RateCard) -> None:
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
