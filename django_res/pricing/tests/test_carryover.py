"""Tests for RateCarryoverService.materialise (the on-demand promote action)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.exceptions import NoRateAvailable
from pricing.models import Currency, RateCard, RatePlan, RateRule
from pricing.services.carryover import RateCarryoverService
from pricing.services.projection import keep_calendar_date
from properties.models import Property


@pytest.fixture
def anchor_rule(property_: Property, gbp: Currency) -> RateRule:
    """A 2026 plan/card/rule to carry forward."""
    plan = RatePlan.objects.create(
        property=property_,
        name="Summer 2026",
        currency=gbp,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        fallback_nightly=Decimal("120.00"),
    )
    card = RateCard.objects.create(plan=plan, name="Peak", sort_order=0, min_nights=7)
    return RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )


@pytest.mark.django_db
def test_materialise_writes_real_rows_for_target_year(
    property_: Property, gbp: Currency, anchor_rule: RateRule
) -> None:
    new_plan = RateCarryoverService.materialise(
        property_,
        target_year=2028,
        currency=gbp,
        date_map=keep_calendar_date,
    )

    assert new_plan.pk != anchor_rule.card.plan.pk
    assert new_plan.effective_from == date(2028, 1, 1)
    assert new_plan.effective_to == date(2028, 12, 31)
    assert new_plan.fallback_nightly == Decimal("120.00")

    card = new_plan.cards.get()
    assert card.name == "Peak"
    assert card.min_nights == 7
    rule = card.rules.get()
    assert rule.date_from == date(2028, 6, 1)
    assert rule.date_to == date(2028, 8, 31)
    assert rule.nightly == Decimal("200.00")
    # A distinct, editable row — not the anchor.
    assert rule.pk != anchor_rule.pk
    assert rule.is_locked is False


@pytest.mark.django_db
def test_materialise_is_idempotent(
    property_: Property, gbp: Currency, anchor_rule: RateRule
) -> None:
    first = RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)
    second = RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)

    assert first.pk == second.pk
    # Anchor (2026) + one materialised (2028) — never duplicated.
    assert RatePlan.objects.filter(property=property_, currency=gbp).count() == 2
    assert RateRule.objects.filter(card__plan=first).count() == 1


@pytest.mark.django_db
def test_materialise_records_provenance(
    property_: Property, gbp: Currency, anchor_rule: RateRule
) -> None:
    new_plan = RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)
    assert f"plan #{anchor_rule.card.plan.pk}" in new_plan.notes
    assert "2026" in new_plan.notes


@pytest.mark.django_db
def test_materialise_applies_uplift(
    property_: Property, gbp: Currency, anchor_rule: RateRule
) -> None:
    new_plan = RateCarryoverService.materialise(
        property_,
        target_year=2028,
        currency=gbp,
        uplift=Decimal("0.10"),
    )
    rule = RateRule.objects.get(card__plan=new_plan)
    assert rule.nightly == Decimal("220.00")


@pytest.mark.django_db
def test_materialise_skips_inactive_cards_and_unapproved_rules(
    property_: Property, gbp: Currency, anchor_rule: RateRule
) -> None:
    """The carried set matches the guide a quote would show — no dormant rows."""
    anchor_plan = anchor_rule.card.plan
    inactive = RateCard.objects.create(
        plan=anchor_plan, name="Inactive", sort_order=1, is_active=False
    )
    RateRule.objects.create(
        card=inactive,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("999.00"),
    )
    RateRule.objects.create(
        card=anchor_rule.card,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
        min_party=1,
        max_party=8,
        nightly=Decimal("888.00"),
        is_approved=False,
    )

    new_plan = RateCarryoverService.materialise(
        property_, target_year=2028, currency=gbp, date_map=keep_calendar_date
    )

    # Only the active card and the approved rule are carried forward.
    assert new_plan.cards.count() == 1
    assert new_plan.cards.get().name == "Peak"
    assert RateRule.objects.filter(card__plan=new_plan).count() == 1


@pytest.mark.django_db
def test_materialise_without_anchor_raises(property_: Property, gbp: Currency) -> None:
    with pytest.raises(NoRateAvailable):
        RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)
