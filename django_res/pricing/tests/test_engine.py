"""Tests for `pricing.services.PricingEngine.quote()`."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.exceptions import NoRateAvailable, PartyOutOfRange
from pricing.enums import ExtraCalc, ExtraKind
from pricing.models import Currency, Extra, RateCard, RatePlan, RateRule
from pricing.services import PricingEngine
from properties.models import Property


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


@pytest.mark.django_db
def test_quote_tiebreak_higher_priority_wins(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    base_card = RateCard.objects.create(plan=plan, name="Base", sort_order=0)
    overlay_card = RateCard.objects.create(plan=plan, name="Overlay", sort_order=1)

    # base: priority 0, broad range
    RateRule.objects.create(
        card=base_card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        priority=0,
        nightly=Decimal("100.00"),
    )
    # overlay: priority 10, narrower range — should win on these dates
    RateRule.objects.create(
        card=overlay_card,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        min_party=1,
        max_party=8,
        priority=10,
        nightly=Decimal("250.00"),
    )

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 14),  # 4 nights, fully inside overlay
        party=4,
        currency=gbp,
    )
    assert all(ln.nightly == Decimal("250.00") for ln in quote.lines)
    assert quote.rate_subtotal == Decimal("1000.00")


@pytest.mark.django_db
def test_quote_tiebreak_equal_priority_narrower_range_wins(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    base_card = RateCard.objects.create(plan=plan, name="Base", sort_order=0)
    overlay_card = RateCard.objects.create(plan=plan, name="Overlay", sort_order=1)

    RateRule.objects.create(
        card=base_card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        priority=5,
        nightly=Decimal("100.00"),
    )
    # Narrower (1 week) — same priority — should win on its nights.
    RateRule.objects.create(
        card=overlay_card,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 16),
        min_party=1,
        max_party=8,
        priority=5,
        nightly=Decimal("180.00"),
    )

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 14),
        party=4,
        currency=gbp,
    )
    assert all(ln.nightly == Decimal("180.00") for ln in quote.lines)


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
        "priority": 0,
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
def test_all_fallback_stay_skips_card_validation(
    property_: Property, gbp: Currency, plan: RatePlan, card: RateCard
) -> None:
    """A stay with no covering rules quotes entirely on fallback; the card's
    min_nights is not validated because no card was selected."""
    plan.fallback_nightly = Decimal("99.00")
    plan.save(update_fields=["fallback_nightly"])
    card.min_nights = 5  # would raise MinNightsNotMet if validated
    card.save(update_fields=["min_nights"])

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 13),  # 3 nights, all uncovered
        party=4,
        currency=gbp,
    )

    assert len(quote.lines) == 3
    assert all(ln.rule_id is None and ln.card_id is None for ln in quote.lines)
    assert quote.rate_subtotal == Decimal("297.00")
    assert quote.breakdown["winning_card_id"] is None


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
