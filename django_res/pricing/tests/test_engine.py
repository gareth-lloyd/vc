"""Tests for `pricing.services.PricingEngine.quote()`."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.exceptions import NoRateAvailable
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
