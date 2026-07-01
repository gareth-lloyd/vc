"""Tests for `pricing.services.PricingEngine.quote()`."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.exceptions import MinNightsNotMet, NoRateAvailable, PartyOutOfRange
from core.tests import assert_max_queries
from pricing.enums import ExtraCalc, ExtraKind
from pricing.models import Currency, Extra, RateCard, RatePeriod, RatePlan, RateRule
from pricing.services import OccupancyBand, PricingContext, PricingEngine
from properties.models import Property, PropertyService


def _period_of(rule: RateRule) -> RatePeriod:
    """The band's shim-derived period (never None once the rule is saved)."""
    period = rule.period
    assert period is not None
    return period


@pytest.mark.django_db
def test_quote_happy_path_single_card_no_extras(
    property_: Property, gbp: Currency, rule: RateRule
) -> None:
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),  # 7 nights
        party=4,
        currency=gbp,
    )

    assert quote.currency_code == "GBP"
    assert len(quote.lines) == 7
    assert all(ln.nightly == Decimal("200.00") for ln in quote.lines)
    assert quote.rate_subtotal == Decimal("1400.00")
    assert quote.extras == []
    assert quote.extras_total == Decimal("0")
    assert quote.discount == Decimal("0.00")
    assert quote.commission == Decimal("0.00")
    assert quote.tax == Decimal("0.00")
    assert quote.total == Decimal("1400.00")
    assert quote.breakdown["lines"][0]["rule_id"] == rule.pk


@pytest.mark.django_db
def test_pricing_engine_writes_net_to_owner_to_snapshot(
    property_: Property, gbp: Currency, rule: RateRule
) -> None:
    """`PricingEngine.quote` materialises `net_to_owner` on the breakdown.

    Owner-net is `total - commission - tax`; the engine computes it once at
    quote time and stamps it on the breakdown so the booking serializer
    (and any other consumer of `Booking.pricing_snapshot`) never has to
    subtract money downstream. The dataclass field carries the same value
    so callers that hold a `Quote` object can read it without inspecting
    the JSON blob.
    """
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )

    expected_net = (quote.total - quote.commission - quote.tax).quantize(Decimal("0.01"))
    assert quote.net_to_owner == expected_net
    assert quote.breakdown["net_to_owner"] == str(expected_net)


@pytest.mark.django_db
def test_quote_applies_mandatory_extra(property_: Property, gbp: Currency, rule: RateRule) -> None:
    Extra.objects.create(
        property=property_,
        name="Cleaning",
        kind=ExtraKind.CLEANING,
        calc=ExtraCalc.FIXED_PER_STAY,
        amount=Decimal("150.00"),
        currency=gbp,
        is_mandatory=True,
    )

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )

    assert len(quote.extras) == 1
    assert quote.extras[0].name == "Cleaning"
    assert quote.extras[0].computed_amount == Decimal("150.00")
    assert quote.extras_total == Decimal("150.00")
    assert quote.total == Decimal("1550.00")


@pytest.mark.django_db
def test_quote_opt_in_extra_only_when_requested(
    property_: Property, gbp: Currency, rule: RateRule
) -> None:
    pet = Extra.objects.create(
        property=property_,
        name="Pet fee",
        kind=ExtraKind.PET_FEE,
        calc=ExtraCalc.FIXED_PER_STAY,
        amount=Decimal("50.00"),
        currency=gbp,
        is_mandatory=False,
    )

    # Without opt-in: extra is not applied.
    quote_no_pet = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )
    assert quote_no_pet.extras == []
    assert quote_no_pet.extras_total == Decimal("0")

    # With opt-in: applied.
    quote_with_pet = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
        opt_in_extras=[pet.pk],
    )
    assert len(quote_with_pet.extras) == 1
    assert quote_with_pet.extras[0].computed_amount == Decimal("50.00")


# GAP-056: cross-card precedence is GONE. Periods are the disjoint date axis —
# at most one active period covers any night (Unit 9 EXCLUDE), so there is no
# "first card wins" / "later card overrides" mechanism left to test. The former
# `test_quote_first_card_by_sort_order_wins` and
# `test_quote_card_order_beats_narrower_range` were removed with the card layer.


@pytest.mark.django_db
def test_quote_occupancy_bracket_matched_not_defaulted_to_highest(
    property_: Property, gbp: Currency, card: RateCard
) -> None:
    """Regression: legacy bug #2 (`09-departures.md`).

    Legacy stored-proc fell through to the highest occupancy bracket when no
    bracket matched the requested party size. The new engine must *match*
    brackets, never default. Three disjoint sibling rules on one card:

      * party=4  → 1-8  bracket (NOT 9-12, NOT 13-16)
      * party=10 → 9-12 bracket
      * party=20 → no bracket matches → raises `PartyOutOfRange`
    """
    common = {
        "card": card,
        "date_from": date(2026, 6, 1),
        "date_to": date(2026, 8, 31),
    }
    rule_small = RateRule.objects.create(
        **common,
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )
    rule_mid = RateRule.objects.create(
        **common,
        min_party=9,
        max_party=12,
        nightly=Decimal("250.00"),
    )
    rule_large = RateRule.objects.create(
        **common,
        min_party=13,
        max_party=16,
        nightly=Decimal("400.00"),
    )

    # party=4 picks the 1-8 bracket — not "default to highest".
    quote_small = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )
    assert all(ln.rule_id == rule_small.pk for ln in quote_small.lines)
    assert all(ln.nightly == Decimal("100.00") for ln in quote_small.lines)

    # party=10 picks the 9-12 bracket.
    quote_mid = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=10,
        currency=gbp,
    )
    assert all(ln.rule_id == rule_mid.pk for ln in quote_mid.lines)
    assert all(ln.nightly == Decimal("250.00") for ln in quote_mid.lines)

    # party=20 is outside every bracket — must raise, not silently default
    # to the highest bracket (the legacy bug).
    with pytest.raises(PartyOutOfRange):
        PricingEngine.quote(
            property=property_,
            date_from=date(2026, 6, 10),
            date_to=date(2026, 6, 17),
            party=20,
            currency=gbp,
        )

    # Sanity: `rule_large` exists but was not selected for either successful
    # quote — guards against a "default-to-highest" implementation passing
    # the first two assertions by accident.
    assert RateRule.objects.filter(pk=rule_large.pk).exists()


@pytest.mark.django_db
def test_quote_raises_no_rate_when_no_card_matches(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    # No RateCard / RateRule at all on the plan.
    with pytest.raises(NoRateAvailable):
        PricingEngine.quote(
            property=property_,
            date_from=date(2026, 6, 10),
            date_to=date(2026, 6, 17),
            party=4,
            currency=gbp,
        )


@pytest.mark.django_db
def test_quote_respects_is_approved_filter(
    property_: Property, gbp: Currency, card: RateCard
) -> None:
    # Unapproved rule must be filtered out → NoRateAvailable.
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
        is_approved=False,
    )

    with pytest.raises(NoRateAvailable):
        PricingEngine.quote(
            property=property_,
            date_from=date(2026, 6, 10),
            date_to=date(2026, 6, 17),
            party=4,
            currency=gbp,
        )

    # Approve it → quote now succeeds.
    RateRule.objects.update(is_approved=True)
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )
    assert quote.rate_subtotal == Decimal("1400.00")


# ---------------------------------------------------------------------------
# GAP-008 — RatePlan.fallback_nightly: price uncovered nights at an opt-in rate
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_fallback_nightly_fills_gap_night(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """A night past the rule's coverage is priced at `fallback_nightly`."""
    plan.fallback_nightly = Decimal("150.00")
    plan.save(update_fields=["fallback_nightly"])

    # rule covers 2026-06-01..2026-08-31; Sep 1 is uncovered.
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 8, 30),
        date_to=date(2026, 9, 2),  # Aug 30, Aug 31 covered; Sep 1 gap
        party=4,
        currency=gbp,
    )

    assert len(quote.lines) == 3
    fallback_lines = [ln for ln in quote.lines if ln.rule_id is None]
    assert len(fallback_lines) == 1
    assert fallback_lines[0].date == date(2026, 9, 1)
    assert fallback_lines[0].card_id is None
    assert fallback_lines[0].nightly == Decimal("150.00")
    assert quote.rate_subtotal == Decimal("550.00")  # 200 + 200 + 150


@pytest.mark.django_db
def test_all_fallback_stay_skips_period_validation(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    """A stay with no covering bands quotes entirely on fallback; no period is
    selected, so the strictest-wins min/max-nights guard is skipped (GAP-056)."""
    plan.fallback_nightly = Decimal("99.00")
    plan.save(update_fields=["fallback_nightly"])

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 13),  # 3 nights, all uncovered (no bands at all)
        party=4,
        currency=gbp,
    )

    assert len(quote.lines) == 3
    assert all(ln.rule_id is None and ln.card_id is None for ln in quote.lines)
    assert quote.rate_subtotal == Decimal("297.00")
    assert quote.breakdown["winning_period_id"] is None


@pytest.mark.django_db
def test_quote_excludes_deactivated_cards_rules(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    """A rule under a deactivated `RateCard` must not price.

    Parity guard for the transitional expand phase: the old engine filtered
    `RateCard.objects.filter(is_active=True)`, and `load_anchor_cards_with_rules`
    (still used by carryover) keeps honouring `card.is_active`. But the `save()`
    shim / backfill stamp every `RatePeriod` `is_active=True` regardless of the
    card, so the period flag can't stand in for card activeness yet — the engine
    must keep gating rules on `card.is_active` while cards exist. (Dropped in
    Unit 9 when `period.is_active` becomes the sole gate.)
    """
    # Withdrawn card + rule created FIRST, so its rule has the lower pk and would
    # win `pick_rule_for_night`'s lowest-pk tie-break if it leaked past the gate.
    withdrawn = RateCard.objects.create(plan=plan, name="Withdrawn", sort_order=0, is_active=False)
    RateRule.objects.create(
        card=withdrawn,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("50.00"),
    )
    live = RateCard.objects.create(plan=plan, name="Live", sort_order=1)
    RateRule.objects.create(
        card=live,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 14),
        party=4,
        currency=gbp,
    )

    # The withdrawn card's 50.00 must never appear — only the live rate prices.
    assert all(ln.nightly == Decimal("200.00") for ln in quote.lines)


@pytest.mark.django_db
def test_gap_night_without_fallback_still_raises(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """`fallback_nightly=None` (default) preserves the hard NoRateAvailable."""
    assert plan.fallback_nightly is None
    with pytest.raises(NoRateAvailable):
        PricingEngine.quote(
            property=property_,
            date_from=date(2026, 8, 30),
            date_to=date(2026, 9, 2),
            party=4,
            currency=gbp,
        )


@pytest.mark.django_db
def test_fallback_does_not_mask_party_out_of_range(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """A party outside every bracket raises even when a fallback is set —
    the fallback covers missing nights, never a bracket miss."""
    plan.fallback_nightly = Decimal("150.00")
    plan.save(update_fields=["fallback_nightly"])
    with pytest.raises(PartyOutOfRange):
        PricingEngine.quote(
            property=property_,
            date_from=date(2026, 6, 10),
            date_to=date(2026, 6, 17),
            party=99,  # rule bracket is 1..8
            currency=gbp,
        )


@pytest.mark.django_db
def test_all_fallback_stay_ignores_other_propertys_card_less_discount(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    """An all-fallback stay must not pick up a *different* property's
    card-less discount.

    With no covering band there is no winning period, so `_apply_discounts`
    runs with `card_id=None`. The property scope must still hold: a card-less
    discount belonging to another property must never apply here. (Regression
    guard — `Q(card_id=card_id)` collapses to `Q(card__isnull=True)` when
    `card_id` is `None`, which would otherwise match every property's card-less
    rule.)
    """
    from pricing.enums import DiscountKind, RuleKind
    from pricing.models import Discount
    from properties.models import Property

    other = Property.objects.create(
        name="Other Villa",
        display_name="Other Villa",
        slug="other-villa",
        category=property_.category,
        group=property_.group,
        region=property_.region,
    )
    Discount.objects.create(
        property=other,
        name="Other LOS",
        rule_kind=RuleKind.LENGTH_OF_STAY,
        kind=DiscountKind.PERCENT,
        amount=Decimal("50.00"),  # would halve the stay if it leaked across
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        is_active=True,
    )

    plan.fallback_nightly = Decimal("100.00")
    plan.save(update_fields=["fallback_nightly"])

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 13),  # 3 uncovered nights (no `rule` fixture)
        party=4,
        currency=gbp,
    )

    assert quote.rate_subtotal == Decimal("300.00")
    assert quote.discount == Decimal("0.00")


# ---------------------------------------------------------------------------
# GAP-007 — changeover auto-shift: nudge a non-conforming arrival forward
# ---------------------------------------------------------------------------
# 2026-06-10 is a Wednesday; 2026-06-13 a Saturday; 2026-06-15 a Monday.
def _changeover_rule(property_: Property, day: str) -> None:
    from properties.enums import PrefilledChangeOverDay
    from properties.models import ChangeOverRule

    ChangeOverRule.objects.create(
        property=property_,
        day=getattr(PrefilledChangeOverDay, day).value,
        starts_on=date(2026, 6, 1),
        ends_on=date(2026, 8, 31),
    )


@pytest.mark.django_db
def test_changeover_shift_via_property_rule(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """A property Saturday-changeover rule nudges a Wednesday arrival to Sat,
    preserving the night count and reporting the original date."""
    _changeover_rule(property_, "SAT")

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),  # Wednesday
        date_to=date(2026, 6, 17),  # 7 nights
        party=4,
        currency=gbp,
    )

    assert quote.changeover_shifted_from == date(2026, 6, 10)
    assert quote.date_from == date(2026, 6, 13)  # next Saturday
    assert quote.date_to == date(2026, 6, 20)  # nights preserved (7)
    assert len(quote.lines) == 7
    assert quote.lines[0].date == date(2026, 6, 13)
    assert quote.breakdown["changeover_shifted_from"] == "2026-06-10"


@pytest.mark.django_db
def test_changeover_shift_with_two_cards_covering_stay(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """Two active cards covering the stay + a property Saturday rule: the
    Wednesday arrival shifts to Saturday and prices cleanly — no per-card
    changeover field, no ChangeoverViolation (regression for GAP-007)."""
    second = RateCard.objects.create(plan=plan, name="Second", sort_order=1)
    RateRule.objects.create(
        card=second,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("250.00"),
    )
    _changeover_rule(property_, "SAT")

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),  # Wednesday
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )

    assert quote.changeover_shifted_from == date(2026, 6, 10)
    assert quote.date_from == date(2026, 6, 13)  # next Saturday
    assert quote.date_to == date(2026, 6, 20)  # nights preserved
    assert len(quote.lines) == 7


@pytest.mark.django_db
def test_no_shift_when_arrival_already_on_weekday(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    _changeover_rule(property_, "SAT")

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 13),  # already Saturday
        date_to=date(2026, 6, 20),
        party=4,
        currency=gbp,
    )

    assert quote.changeover_shifted_from is None
    assert quote.date_from == date(2026, 6, 13)
    assert quote.breakdown["changeover_shifted_from"] is None


@pytest.mark.django_db
def test_no_shift_when_no_changeover_rules(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """Zero ChangeOverRule rows + no card weekday → any day, no shift."""
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),  # Wednesday
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )

    assert quote.changeover_shifted_from is None
    assert quote.date_from == date(2026, 6, 10)


@pytest.mark.django_db
def test_repeat_guest_discount_never_applied(
    property_: Property, gbp: Currency, rule: RateRule
) -> None:
    """REPEAT_GUEST is a recognised-but-unimplemented enum (GAP-009).

    A `REPEAT_GUEST` discount that would otherwise match (active, in-window,
    min_nights satisfied) must never reduce the total — the engine excludes
    it at the queryset, so it can't silently mis-apply.
    """
    from pricing.enums import DiscountKind, RuleKind
    from pricing.models import Discount

    Discount.objects.create(
        property=property_,
        name="Welcome back",
        rule_kind=RuleKind.REPEAT_GUEST,
        kind=DiscountKind.PERCENT,
        amount=Decimal("50.00"),  # would halve the stay if applied
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        is_active=True,
    )

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),  # 7 nights x 200 = 1400
        party=4,
        currency=gbp,
    )

    assert quote.discount == Decimal("0.00")
    assert quote.total == Decimal("1400.00")


# --- Lazy projection for future years (no real plan) ------------------------


@pytest.mark.django_db
def test_quote_projects_from_prior_year_when_no_plan(
    property_: Property, gbp: Currency, rule: RateRule
) -> None:
    """A 2028 stay with only a 2026 plan derives a guide rate from 2026."""
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2028, 7, 4),
        date_to=date(2028, 7, 11),
        party=4,
        currency=gbp,
    )

    assert quote.is_projected is True
    assert len(quote.lines) == 7
    assert all(ln.nightly == Decimal("200.00") for ln in quote.lines)
    # Lines reference the real 2026 source rule for traceability.
    assert all(ln.rule_id == rule.pk for ln in quote.lines)
    assert quote.breakdown["is_projected"] is True
    assert quote.breakdown["projection"]["source_year"] == 2026
    assert quote.breakdown["projection"]["target_year"] == 2028
    assert quote.breakdown["projection"]["source_plan_id"] == rule.card.plan.pk


@pytest.mark.django_db
def test_quote_prefers_real_plan_over_projection(
    property_: Property, gbp: Currency, rule: RateRule
) -> None:
    """A real plan covering the stay wins; projection never runs."""
    plan_2028 = RatePlan.objects.create(
        property=property_,
        name="Summer 2028",
        currency=gbp,
        effective_from=date(2028, 1, 1),
        effective_to=date(2028, 12, 31),
    )
    card_2028 = RateCard.objects.create(plan=plan_2028, name="Default", sort_order=0)
    RateRule.objects.create(
        card=card_2028,
        date_from=date(2028, 6, 1),
        date_to=date(2028, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("250.00"),
    )

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2028, 7, 4),
        date_to=date(2028, 7, 11),
        party=4,
        currency=gbp,
    )

    assert quote.is_projected is False
    assert all(ln.nightly == Decimal("250.00") for ln in quote.lines)
    assert quote.breakdown["projection"] is None


@pytest.mark.django_db
def test_quote_not_projected_for_a_normal_in_year_stay(
    property_: Property, gbp: Currency, rule: RateRule
) -> None:
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )
    assert quote.is_projected is False
    assert quote.breakdown["is_projected"] is False


@pytest.mark.django_db
def test_quote_no_projection_without_anchor_raises(property_: Property, gbp: Currency) -> None:
    with pytest.raises(NoRateAvailable):
        PricingEngine.quote(
            property=property_,
            date_from=date(2028, 7, 4),
            date_to=date(2028, 7, 11),
            party=4,
            currency=gbp,
        )


@pytest.mark.django_db
def test_quote_allow_projection_false_raises_even_with_anchor(
    property_: Property, gbp: Currency, rule: RateRule
) -> None:
    with pytest.raises(NoRateAvailable):
        PricingEngine.quote(
            property=property_,
            date_from=date(2028, 7, 4),
            date_to=date(2028, 7, 11),
            party=4,
            currency=gbp,
            allow_projection=False,
        )


# ---------------------------------------------------------------------------
# Breakdown enrichment — plan/card metadata the quote builder renders on each
# result line (inclusion, changeover day, min/max nights, occupancy pricing).
# All sourced from objects already in memory at quote time: zero extra queries.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_breakdown_carries_property_service_inclusion(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """The property's date-banded PropertyService copy rides on the breakdown so
    the builder can seed staged-line inclusions from it (legacy ResService.cs:1241
    seeded line inclusions from the season)."""
    PropertyService.objects.create(
        property=property_, name="Maid", copy="Daily maid service, pool heating"
    )

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )

    assert quote.breakdown["inclusion"] == "Daily maid service, pool heating"


@pytest.mark.django_db
def test_inclusion_reflects_service_date_band(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """A summer-only chef joins a year-round housekeeping service in July but
    drops out in autumn — inclusions vary by stay date, not by rate season."""
    PropertyService.objects.create(
        property=property_, name="Housekeeping", copy="Daily housekeeping.", sort_order=0
    )
    PropertyService.objects.create(
        property=property_,
        name="Chef",
        copy="Private chef.",
        sort_order=1,
        applies_from=date(2026, 6, 1),
        applies_to=date(2026, 8, 31),
    )

    july = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 7, 4),
        date_to=date(2026, 7, 11),
        party=4,
        currency=gbp,
    )
    assert july.breakdown["inclusion"] == "Daily housekeeping.\nPrivate chef."

    # An out-of-band stay needs its own plan; reuse the same villa in November.
    RateRule.objects.create(
        card=rule.card,
        date_from=date(2026, 11, 1),
        date_to=date(2026, 11, 30),
        min_party=1,
        max_party=8,
        nightly=Decimal("150.00"),
    )
    november = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 11, 7),
        date_to=date(2026, 11, 14),
        party=4,
        currency=gbp,
    )
    assert november.breakdown["inclusion"] == "Daily housekeeping."


@pytest.mark.django_db
def test_inactive_service_excluded_from_inclusions(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """A deactivated service drops out of the inclusion blob."""
    PropertyService.objects.create(
        property=property_, name="Chef", copy="Private chef.", is_active=False
    )

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )
    assert quote.breakdown["inclusion"] == ""


@pytest.mark.django_db
def test_projected_quote_remaps_inclusions_to_anchor_year(
    property_: Property, gbp: Currency, rule: RateRule
) -> None:
    """F1 guard: a future-year July quote, priced by projecting the 2026 anchor,
    still surfaces the summer chef whose absolute band sits in 2026."""
    PropertyService.objects.create(
        property=property_, name="Housekeeping", copy="Daily housekeeping.", sort_order=0
    )
    PropertyService.objects.create(
        property=property_,
        name="Chef",
        copy="Private chef.",
        sort_order=1,
        applies_from=date(2026, 6, 1),
        applies_to=date(2026, 8, 31),
    )

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2028, 7, 4),
        date_to=date(2028, 7, 11),
        party=4,
        currency=gbp,
    )

    assert quote.is_projected is True
    assert quote.breakdown["inclusion"] == "Daily housekeeping.\nPrivate chef."


@pytest.mark.django_db
def test_breakdown_changeover_day_code(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    _changeover_rule(property_, "SAT")

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 13),  # Saturday
        date_to=date(2026, 6, 20),
        party=4,
        currency=gbp,
    )

    assert quote.breakdown["changeover_day"] == "sat"


@pytest.mark.django_db
def test_breakdown_changeover_day_null_when_unconstrained(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """`any` / no constraint serialises as null, not the literal "any" code."""
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )

    assert quote.breakdown["changeover_day"] is None


@pytest.mark.django_db
def test_breakdown_min_max_nights_from_winning_period(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """min/max-nights now live on the period (GAP-056); the breakdown reports
    the winning period's own overrides."""
    period = _period_of(rule)
    period.min_nights = 5
    period.max_nights = 14
    period.save(update_fields=["min_nights", "max_nights"])

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )

    assert quote.breakdown["min_nights"] == 5
    assert quote.breakdown["max_nights"] == 14


@pytest.mark.django_db
def test_breakdown_min_max_nights_null_on_all_fallback_stay(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    """No winning period (all-fallback stay) → no constraints to report."""
    plan.fallback_nightly = Decimal("99.00")
    plan.save(update_fields=["fallback_nightly"])

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 13),  # all uncovered by the (absent) bands
        party=4,
        currency=gbp,
    )

    assert quote.breakdown["winning_period_id"] is None
    assert quote.breakdown["min_nights"] is None
    assert quote.breakdown["max_nights"] is None
    assert quote.breakdown["occupancy_pricing"] is False


@pytest.mark.django_db
def test_breakdown_occupancy_pricing_false_for_single_band(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )

    assert quote.breakdown["occupancy_pricing"] is False


@pytest.mark.django_db
def test_breakdown_occupancy_pricing_true_for_multiple_party_bands(
    property_: Property, gbp: Currency, plan: RatePlan, card: RateCard, rule: RateRule
) -> None:
    """>1 distinct (min_party, max_party) band on the winning card means the
    price depends on the party size — the builder badges these results."""
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=9,
        max_party=12,
        nightly=Decimal("260.00"),
    )

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )

    assert quote.breakdown["occupancy_pricing"] is True


@pytest.mark.django_db
def test_breakdown_occupancy_pricing_false_for_same_band_split_dates(
    property_: Property, gbp: Currency, plan: RatePlan, card: RateCard, rule: RateRule
) -> None:
    """Seasonal date splits with the SAME party band are not occupancy pricing
    — only distinct bands count."""
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 10, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("180.00"),
    )

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )

    assert quote.breakdown["occupancy_pricing"] is False


# ----------------------------------------------------------------------
# load_context / stay_length_bounds — pre-pricing card aggregates for
# block selection, on a context the caller can feed back into quote()
# ----------------------------------------------------------------------


def _june_context(property_: Property) -> PricingContext | None:
    return PricingEngine.load_context(
        property_, date_from=date(2026, 6, 10), date_to=date(2026, 6, 17)
    )


@pytest.mark.django_db
def test_stay_length_bounds_single_period(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    period = _period_of(rule)
    period.min_nights = 5
    period.max_nights = 14
    period.save(update_fields=["min_nights", "max_nights"])

    context = _june_context(property_)
    assert context is not None

    assert PricingEngine.stay_length_bounds(context) == (5, 14)


@pytest.mark.django_db
def test_stay_length_bounds_aggregates_across_periods(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """A stay is valid if ANY period accepts it, so the search-layer bounds are
    the LOOSEST across the plan's active periods — an uncapped period uncaps the
    lot (GAP-056 decision 4; this is the permissive pre-filter, not the guard)."""
    peak = _period_of(rule)  # covers June (2026-06-01..08-31)
    peak.min_nights = 7
    peak.max_nights = 14
    peak.save(update_fields=["min_nights", "max_nights"])

    # A second, off-peak period on the same plan with a shorter min and no cap.
    off_peak = _period_of(
        RateRule.objects.create(
            card=rule.card,
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 30),
            min_party=1,
            max_party=8,
            nightly=Decimal("120.00"),
        )
    )
    off_peak.min_nights = 3
    off_peak.save(update_fields=["min_nights"])

    context = _june_context(property_)
    assert context is not None

    assert PricingEngine.stay_length_bounds(context) == (3, None)


@pytest.mark.django_db
def test_divergent_period_min_nights_strict_in_quote_but_loose_in_search(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateRule
) -> None:
    """The headline seasonal min-stay feature (GAP-056 decision 4): a villa with
    a 7-night peak period and a 3-night off-peak period.

    * `stay_length_bounds` is LOOSEST-wins → (3, None), so the search enumerates
      the valid short off-peak blocks (clipping them to 7 would kill the feature).
    * `quote()` is STRICTEST-wins per touched period → a 4-night peak stay is
      rejected, while a 4-night off-peak stay prices fine.
    """
    peak = _period_of(rule)  # 2026-06-01..08-31
    peak.min_nights = 7
    peak.save(update_fields=["min_nights"])

    off_peak = _period_of(
        RateRule.objects.create(
            card=rule.card,
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31),
            min_party=1,
            max_party=8,
            nightly=Decimal("120.00"),
        )
    )
    off_peak.min_nights = 3
    off_peak.save(update_fields=["min_nights"])

    context = _june_context(property_)
    assert context is not None
    # Loosest-wins search pre-filter.
    assert PricingEngine.stay_length_bounds(context) == (3, None)

    # Strictest-wins loud guard: 4 nights in the 7-night peak period is rejected.
    with pytest.raises(MinNightsNotMet):
        PricingEngine.quote(
            property=property_,
            date_from=date(2026, 6, 10),
            date_to=date(2026, 6, 14),  # 4 nights, all in peak
            party=4,
            currency=gbp,
        )

    # The same length in the 3-night off-peak period prices fine.
    off_peak_quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 10, 5),
        date_to=date(2026, 10, 9),  # 4 nights, all in off-peak
        party=4,
        currency=gbp,
    )
    assert len(off_peak_quote.lines) == 4


@pytest.mark.django_db
def test_load_context_none_without_covering_plan(property_: Property, gbp: Currency) -> None:
    """No real plan (the projection path) → None: callers skip the clamp and
    the engine remains the loud guard at pricing time."""
    assert _june_context(property_) is None


@pytest.mark.django_db
def test_load_context_none_when_plan_has_no_active_cards(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    assert _june_context(property_) is None


@pytest.mark.django_db
def test_quote_reuses_a_preloaded_context_without_rate_queries(
    property_: Property, gbp: Currency, plan: RatePlan, card: RateCard, rule: RateRule
) -> None:
    """A caller-supplied context skips the plan/card/rule loads entirely and
    prices identically to a self-loading quote."""
    baseline = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
    )
    context = PricingEngine.load_context(
        property_, date_from=date(2026, 6, 10), date_to=date(2026, 6, 17), currency=gbp
    )
    assert context is not None

    # Changeover/extras/discounts/services still hit the DB; the rate triple
    # must not (services derive the GAP-037 inclusion blob — one property query).
    with assert_max_queries(4):
        reused = PricingEngine.quote(
            property=property_,
            date_from=date(2026, 6, 10),
            date_to=date(2026, 6, 17),
            party=4,
            currency=gbp,
            context=context,
        )

    assert reused.total == baseline.total
    assert reused.breakdown == baseline.breakdown


# ---------------------------------------------------------------------------
# GAP-044 — `PricingEngine.covering_bands`: party-independent band enumerator
# ---------------------------------------------------------------------------


def _three_band_card(card: RateCard) -> None:
    """Seed `card` with three disjoint sibling brackets over June-Aug 2026."""
    common = {"card": card, "date_from": date(2026, 6, 1), "date_to": date(2026, 8, 31)}
    RateRule.objects.create(**common, min_party=1, max_party=8, nightly=Decimal("100.00"))
    RateRule.objects.create(**common, min_party=9, max_party=12, nightly=Decimal("250.00"))
    RateRule.objects.create(**common, min_party=13, max_party=16, nightly=Decimal("400.00"))


@pytest.mark.django_db
def test_covering_bands_returns_all_brackets_sorted(
    property_: Property, gbp: Currency, card: RateCard
) -> None:
    """A 3-bracket card yields all three bands sorted by `min_party`, regardless
    of the party the caller happens to hold — the builder fans them all out."""
    _three_band_card(card)

    bands = PricingEngine.covering_bands(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        currency=gbp,
    )

    assert bands == [
        OccupancyBand(min_party=1, max_party=8),
        OccupancyBand(min_party=9, max_party=12),
        OccupancyBand(min_party=13, max_party=16),
    ]


@pytest.mark.django_db
def test_covering_bands_excludes_bracket_not_covering_every_night(
    property_: Property, gbp: Currency, card: RateCard
) -> None:
    """A bracket whose rule does not span every night of the week is dropped —
    night-correct coverage (rule dates inclusive, nights half-open)."""
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )
    # 9-12 bracket only covers the first few nights of a 10th-17th stay.
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 12),
        min_party=9,
        max_party=12,
        nightly=Decimal("250.00"),
    )

    bands = PricingEngine.covering_bands(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),  # nights 10..16; the 16th is outside 9-12's rule
        currency=gbp,
    )

    assert bands == [OccupancyBand(min_party=1, max_party=8)]


@pytest.mark.django_db
def test_covering_bands_single_bracket_returns_one(
    property_: Property, gbp: Currency, rule: RateRule
) -> None:
    """A single-bracket card returns exactly one band — the ≥2 fan-out threshold
    is the caller's decision, not the enumerator's."""
    bands = PricingEngine.covering_bands(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        currency=gbp,
    )

    assert bands == [OccupancyBand(min_party=1, max_party=8)]


# GAP-056: `test_covering_bands_respects_card_precedence` removed — cross-card
# precedence is gone. Bands are pooled across the plan's (disjoint) periods and a
# bracket is offered iff its own bands cover every night; there is no
# "first card wins" merge rule left to assert.


@pytest.mark.django_db
def test_covering_bands_loads_context_when_none(
    property_: Property, gbp: Currency, card: RateCard
) -> None:
    """With `context=None` (a flexible-changeover villa) the helper loads its own
    context rather than reading a bare attribute off `None` (fixes B1)."""
    _three_band_card(card)

    bands = PricingEngine.covering_bands(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        currency=gbp,
        context=None,
    )

    assert [b.min_party for b in bands] == [1, 9, 13]


@pytest.mark.django_db
def test_covering_bands_empty_when_no_plan_covers(property_: Property, gbp: Currency) -> None:
    """No real plan over the week → no bands (projection is out of scope; a
    guide-rate year has no banded default)."""
    bands = PricingEngine.covering_bands(
        property=property_,
        date_from=date(2030, 6, 10),
        date_to=date(2030, 6, 17),
        currency=gbp,
    )

    assert bands == []


@pytest.mark.django_db
def test_covering_bands_reuses_supplied_context_without_rate_reload(
    property_: Property, gbp: Currency, card: RateCard
) -> None:
    """A supplied context is used as-is — the enumerator never re-reads the
    rate plan/cards/rules. Proven by deleting every rule row after the context
    is loaded: the bands still resolve, so they came from the in-memory context
    (an `assert_max_queries(0)` pin is impossible because F3's changeover shift
    always queries the DB, exactly as a per-band `quote()` would)."""
    _three_band_card(card)
    context = PricingEngine.load_context(
        property_, date_from=date(2026, 6, 10), date_to=date(2026, 6, 17), currency=gbp
    )
    assert context is not None

    # Nuke the source rows: a helper that re-queried would now return nothing.
    RateRule.objects.all().delete()

    bands = PricingEngine.covering_bands(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        currency=gbp,
        context=context,
    )

    assert [(b.min_party, b.max_party) for b in bands] == [(1, 8), (9, 12), (13, 16)]


@pytest.mark.django_db
def test_covering_bands_unions_split_season_rules_for_one_bracket(
    property_: Property, gbp: Currency, card: RateCard
) -> None:
    """Two rules sharing one `(min, max)` bracket over adjacent date ranges that
    together — but neither alone — cover the week still yield that band: coverage
    is per-bracket union, not per-rule."""
    # Base full-range bracket so the card covers the week and there are ≥2 bands.
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )
    # The 9-12 bracket is split into adjacent (non-overlapping) ranges: neither
    # half spans nights 10..16, but their union does (A covers 10-13 inclusive,
    # B covers 14-16). The no_overlap exclusion constraint forbids sharing a day.
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 13),
        min_party=9,
        max_party=12,
        nightly=Decimal("250.00"),
    )
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 14),
        date_to=date(2026, 8, 31),
        min_party=9,
        max_party=12,
        nightly=Decimal("250.00"),
    )

    bands = PricingEngine.covering_bands(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        currency=gbp,
    )

    assert bands == [
        OccupancyBand(min_party=1, max_party=8),
        OccupancyBand(min_party=9, max_party=12),
    ]


@pytest.mark.django_db
def test_covering_bands_includes_bracket_whose_rule_ends_on_last_night(
    property_: Property, gbp: Currency, card: RateCard
) -> None:
    """A bracket whose rule `date_to` equals the stay's last night is INCLUDED —
    rule dates are inclusive on both ends, so coverage must use `<=` not `<`."""
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )
    # 10th-17th stay → nights 10..16; this rule ends exactly on the 16th.
    RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 16),
        min_party=9,
        max_party=12,
        nightly=Decimal("250.00"),
    )

    bands = PricingEngine.covering_bands(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        currency=gbp,
    )

    assert bands == [
        OccupancyBand(min_party=1, max_party=8),
        OccupancyBand(min_party=9, max_party=12),
    ]


@pytest.mark.django_db
def test_covering_bands_pools_bracket_rules_across_periods(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    """A bracket is offered iff ITS OWN bands — pooled across every period the
    week spans — cover all nights (GAP-056). Here the 1-8 bracket has one band
    that lapses mid-week and one that spans it: pooled, the bracket still covers
    the week and is offered alongside the full-span 9-12 / 13-16 brackets."""
    # A 1-8 band that lapses mid-week (misses nights 13..16) on its own period.
    lapsing = RateCard.objects.create(plan=plan, name="Short", sort_order=0)
    RateRule.objects.create(
        card=lapsing,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 12),
        min_party=1,
        max_party=8,
        nightly=Decimal("150.00"),
    )
    # A full-week three-bracket card (its own period) — its 1-8 band spans the gap.
    full = RateCard.objects.create(plan=plan, name="Full", sort_order=1)
    _three_band_card(full)

    bands = PricingEngine.covering_bands(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        currency=gbp,
    )

    assert bands == [
        OccupancyBand(min_party=1, max_party=8),
        OccupancyBand(min_party=9, max_party=12),
        OccupancyBand(min_party=13, max_party=16),
    ]


@pytest.mark.django_db
def test_covering_bands_aligns_non_conforming_arrival_to_changeover_day(
    property_: Property, gbp: Currency, card: RateCard
) -> None:
    """F3: the enumerator applies the same changeover forward-shift as `quote()`
    before choosing nights, so the bands match the night-set each band's own
    `quote()` would price. Here the card's rules only span the SHIFTED week
    (Sat 13th → Sat 20th); a raw Wednesday-based night-set would fall outside
    them and yield no bands, so a non-empty result proves the shift happened."""
    _changeover_rule(property_, "SAT")
    # Rules cover only 6/13..6/20 — the Saturday-aligned week, not the raw
    # Wed 6/10..6/17 arrival the caller passes.
    for min_p, max_p, rate in [(1, 8, "100.00"), (9, 12, "250.00")]:
        RateRule.objects.create(
            card=card,
            date_from=date(2026, 6, 13),
            date_to=date(2026, 6, 20),
            min_party=min_p,
            max_party=max_p,
            nightly=Decimal(rate),
        )

    bands = PricingEngine.covering_bands(
        property=property_,
        date_from=date(2026, 6, 10),  # Wednesday — non-conforming
        date_to=date(2026, 6, 17),
        currency=gbp,
    )

    assert bands == [
        OccupancyBand(min_party=1, max_party=8),
        OccupancyBand(min_party=9, max_party=12),
    ]
