"""Tests for RateCarryoverService.materialise (the on-demand promote action)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.exceptions import NoRateAvailable
from pricing.models import Currency, RateCard, RatePlan, RateRule
from pricing.services.carryover import RateCarryoverService
from pricing.services.projection import (
    RateProjectionService,
    keep_calendar_date,
    shift_to_changeover_weekday,
)
from pricing.services.rates import Picked, nights, pick_rule_for_night, rule_nightly
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


@pytest.mark.django_db
def test_materialise_clips_date_map_collisions(property_: Property, gbp: Currency) -> None:
    """A leap-year anchor range spanning Feb 29 lands one day longer relative
    to its neighbour after mapping (span is preserved, Feb 29 isn't), so the
    shifted ranges collide on the boundary. materialise must clip the later
    rule instead of tripping raterule_no_overlap with an IntegrityError."""
    plan = RatePlan.objects.create(
        property=property_,
        name="2024",
        currency=gbp,
        effective_from=date(2024, 1, 1),
        effective_to=date(2024, 12, 31),
    )
    card = RateCard.objects.create(plan=plan, name="Default", sort_order=0)
    RateRule.objects.create(
        card=card,
        date_from=date(2024, 2, 25),
        date_to=date(2024, 2, 29),  # spans Feb 29
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )
    RateRule.objects.create(
        card=card,
        date_from=date(2024, 3, 1),
        date_to=date(2024, 3, 7),
        min_party=1,
        max_party=8,
        nightly=Decimal("150.00"),
    )

    new_plan = RateCarryoverService.materialise(
        property_, target_year=2025, currency=gbp, date_map=keep_calendar_date
    )

    new_rules = list(
        RateRule.objects.filter(card__plan=new_plan).order_by("date_from"),
    )
    assert [(r.date_from, r.date_to) for r in new_rules] == [
        (date(2025, 2, 25), date(2025, 3, 1)),  # span preserved across the lost Feb 29
        (date(2025, 3, 2), date(2025, 3, 7)),  # clipped off the collided boundary day
    ]


@pytest.mark.django_db
def test_materialise_splits_around_earlier_rule(property_: Property, gbp: Currency) -> None:
    """The weekday map can shift neighbours in opposite directions across a
    leap boundary (here ±3 days at year_delta=3), so a later rule's mapped
    range can extend on *both* sides of an earlier rule's claim. The free
    leading segment must survive as its own row — not be discarded by a
    forward-only clip."""
    plan = RatePlan.objects.create(
        property=property_,
        name="2024",
        currency=gbp,
        effective_from=date(2024, 1, 1),
        effective_to=date(2024, 12, 31),
    )
    card = RateCard.objects.create(plan=plan, name="Default", sort_order=0)
    RateRule.objects.create(
        card=card,
        date_from=date(2024, 2, 26),  # Mon → maps +3 to Mon 1 Mar 2027
        date_to=date(2024, 2, 29),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )
    RateRule.objects.create(
        card=card,
        date_from=date(2024, 3, 1),  # Fri → maps -3 to Fri 26 Feb 2027
        date_to=date(2024, 3, 10),
        min_party=1,
        max_party=8,
        nightly=Decimal("150.00"),
    )

    new_plan = RateCarryoverService.materialise(
        property_, target_year=2027, currency=gbp, date_map=shift_to_changeover_weekday
    )

    new_rules = list(RateRule.objects.filter(card__plan=new_plan).order_by("date_from"))
    # Rule A claims [1 Mar - 4 Mar]; rule B ([26 Feb - 7 Mar] mapped) keeps
    # both remainders around it.
    assert [(r.date_from, r.date_to, r.nightly) for r in new_rules] == [
        (date(2027, 2, 26), date(2027, 2, 28), Decimal("150.00")),
        (date(2027, 3, 1), date(2027, 3, 4), Decimal("100.00")),
        (date(2027, 3, 5), date(2027, 3, 7), Decimal("150.00")),
    ]


@pytest.mark.django_db
def test_materialise_matches_projection_night_by_night(property_: Property, gbp: Currency) -> None:
    """materialise's contract: the rows it writes price every night exactly as
    the in-memory projection would have. Collisions resolve to the lowest
    source pk in both paths — even when pk order disagrees with date order."""
    plan = RatePlan.objects.create(
        property=property_,
        name="2024",
        currency=gbp,
        effective_from=date(2024, 1, 1),
        effective_to=date(2024, 12, 31),
    )
    card = RateCard.objects.create(plan=plan, name="Default", sort_order=0)
    # Lower pk, *later* dates — entered first.
    RateRule.objects.create(
        card=card,
        date_from=date(2024, 3, 1),
        date_to=date(2024, 3, 7),
        min_party=1,
        max_party=8,
        nightly=Decimal("150.00"),
    )
    # Higher pk, earlier dates; spans Feb 29 so its mapped range collides on 1 Mar.
    RateRule.objects.create(
        card=card,
        date_from=date(2024, 2, 25),
        date_to=date(2024, 2, 29),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )

    ctx = RateProjectionService.project(
        property=property_,
        date_from=date(2025, 2, 1),
        currency=gbp,
        date_map=keep_calendar_date,
    )
    assert ctx is not None

    new_plan = RateCarryoverService.materialise(
        property_, target_year=2025, currency=gbp, date_map=keep_calendar_date
    )
    mat_cards = list(
        RateCard.objects.filter(plan=new_plan, is_active=True).order_by("sort_order", "pk")
    )
    mat_rules = {c.pk: list(c.rules.all()) for c in mat_cards}

    for night in nights(date(2025, 2, 25), date(2025, 3, 8)):
        projected = pick_rule_for_night(ctx.cards, ctx.rules_by_card, night, party=4)
        materialised = pick_rule_for_night(mat_cards, mat_rules, night, party=4)
        assert type(projected) is type(materialised), night
        if isinstance(projected, Picked):
            assert isinstance(materialised, Picked)
            assert rule_nightly(projected.rule) == rule_nightly(materialised.rule), night
