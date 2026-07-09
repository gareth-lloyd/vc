"""BUG-009 — the engine's commission/tax maths are `RatePlan.price_basis`-aware.

GROSS: the rate already includes commission+tax — carve them out, never add
on top (`total == base`). NET: gross up (`total = base + commission + tax`).
Spec: `04-pricing.md` Services steps 8-10; legacy ground truth
`RatesModel.Calculate()`. Quantization order is pinned: the RAW (unquantized)
commission feeds the tax base, each component quantizes to 0.01 at the end —
matching `frontend/src/lib/pricing/netGross.ts` (GAP-035).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pricing.enums import DiscountKind, ExtraCalc, ExtraKind, PriceBasis, RuleKind
from pricing.models import Currency, Discount, Extra, RateBand, RatePeriod, RatePlan
from pricing.services import PricingEngine
from pricing.services.quote import Quote
from properties.enums import CommissionCalcType
from properties.models import Property, PropertyFinance

pytestmark = pytest.mark.django_db


def _quote(
    property_: Property,
    currency: Currency,
    *,
    discount_code: str | None = None,
    date_to: date = date(2026, 6, 17),
) -> Quote:
    """A stay from 10 Jun 2026 for party 4 — 7 nights x the fixture nightly
    unless ``date_to`` stretches it."""
    return PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date_to,
        party=4,
        currency=currency,
        discount_code=discount_code,
    )


def _finance(
    property_: Property,
    *,
    commission_type: str | None = CommissionCalcType.PERCENT,
    commission_amount: str | None = "15",
    tax_percentage: str | None = "10",
    tax_is_exempt: bool = False,
) -> PropertyFinance:
    return PropertyFinance.objects.create(
        property=property_,
        commission_calculation_type=commission_type,
        commission_amount=Decimal(commission_amount) if commission_amount is not None else None,
        tax_percentage=Decimal(tax_percentage) if tax_percentage is not None else None,
        tax_is_exempt=tax_is_exempt,
    )


def _set_basis(plan: RatePlan, basis: PriceBasis) -> None:
    plan.price_basis = basis
    plan.save(update_fields=["price_basis"])


# --- GROSS carve-out ---------------------------------------------------------


def test_gross_plan_carves_out_commission_and_tax(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """GROSS: tax = basexrate; commission = (base-tax)xpct; total == base."""
    _finance(property_)  # 15% commission, 10% tax

    quote = _quote(property_, gbp)

    assert quote.rate_subtotal == Decimal("1400.00")
    assert quote.tax == Decimal("140.00")  # 1400 x 10%
    assert quote.commission == Decimal("189.00")  # (1400 - 140) x 15%
    assert quote.total == Decimal("1400.00")  # the guest pays the gross
    assert quote.net_to_owner == Decimal("1071.00")  # 1400 - 140 - 189
    assert quote.breakdown["total"] == "1400.00"
    assert quote.breakdown["commission"] == "189.00"
    assert quote.breakdown["tax"] == "140.00"
    assert quote.breakdown["net_to_owner"] == "1071.00"
    # Plans are mutable — the persisted snapshot records the mode it priced in.
    assert quote.breakdown["price_basis"] == PriceBasis.GROSS


def test_gross_plan_fixed_commission_is_flat(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """A fixed commission deducts the flat amount from owner-net (legacy parity).

    Closes the old "fixed → 0.00" divergence: the guest total is untouched
    (still the gross), but `net_to_owner` now carries the deduction.
    """
    _finance(property_, commission_type=CommissionCalcType.FIXED, commission_amount="100")

    quote = _quote(property_, gbp)

    assert quote.tax == Decimal("140.00")
    assert quote.commission == Decimal("100.00")
    assert quote.total == Decimal("1400.00")
    assert quote.net_to_owner == Decimal("1160.00")


def test_gross_fixed_commission_can_drive_net_negative(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """Owner-net may go negative on a GROSS plan — a real deficit, kept as-is."""
    _finance(property_, commission_type=CommissionCalcType.FIXED, commission_amount="1500")

    quote = _quote(property_, gbp)

    assert quote.total == Decimal("1400.00")
    assert quote.net_to_owner == Decimal("-240.00")  # 1400 - 140 - 1500


def test_gross_extras_and_discount_fold_into_base(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """The mode maths apply to base = rate_subtotal + extras - discount."""
    _finance(property_)
    Extra.objects.create(
        property=property_,
        currency=gbp,
        name="Cleaning",
        kind=ExtraKind.CLEANING,
        calc=ExtraCalc.FIXED_PER_STAY,
        is_mandatory=True,
        amount=Decimal("150.00"),
        is_active=True,
    )
    Discount.objects.create(
        property=property_,
        name="Promo",
        code="FOLD50",
        rule_kind=RuleKind.PROMO_CODE,
        kind=DiscountKind.FIXED,
        amount=Decimal("50.00"),
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        is_active=True,
    )

    quote = _quote(property_, gbp, discount_code="FOLD50")

    # base = 1400 + 150 - 50 = 1500
    assert quote.tax == Decimal("150.00")
    assert quote.commission == Decimal("202.50")  # (1500 - 150) x 15%
    assert quote.total == Decimal("1500.00")
    assert quote.net_to_owner == Decimal("1147.50")


# --- NET gross-up ------------------------------------------------------------


def test_net_plan_grosses_up_commission_and_tax(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """NET: commission = base/(1-pct)-base; tax on (base + raw commission)."""
    _finance(property_)
    _set_basis(rule.period.plan, PriceBasis.NET)

    quote = _quote(property_, gbp)

    assert quote.commission == Decimal("247.06")  # 1400/0.85 - 1400
    assert quote.tax == Decimal("183.01")  # (1400 + 247.0588…)/0.9 - (…)
    assert quote.total == Decimal("1830.07")  # 1400 + 247.06 + 183.01
    assert quote.net_to_owner == Decimal("1400.00")


def test_net_gross_up_feeds_raw_commission_into_tax_base(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """Quantization order pin: the RAW commission feeds the tax base.

    7 x 100.51 = 703.57 @ 15.25% commission / 9.50% tax: raw commission
    126.6015… → tax 87.15. Quantizing the commission first (126.60) would
    give 87.14 — this case distinguishes the two orders by a cent.
    """
    _finance(property_, commission_amount="15.25", tax_percentage="9.50")
    plan = rule.period.plan
    _set_basis(plan, PriceBasis.NET)
    rule.nightly = Decimal("100.51")
    rule.save(update_fields=["nightly"])

    quote = _quote(property_, gbp)

    assert quote.rate_subtotal == Decimal("703.57")
    assert quote.commission == Decimal("126.60")
    assert quote.tax == Decimal("87.15")  # not 87.14
    assert quote.total == Decimal("917.32")


def test_net_plan_fixed_commission_enters_tax_base(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """NET + fixed: flat commission, and it sits inside the tax base (legacy)."""
    _finance(property_, commission_type=CommissionCalcType.FIXED, commission_amount="100")
    _set_basis(rule.period.plan, PriceBasis.NET)

    quote = _quote(property_, gbp)

    assert quote.commission == Decimal("100.00")
    assert quote.tax == Decimal("166.67")  # (1400 + 100)/0.9 - 1500
    assert quote.total == Decimal("1666.67")
    assert quote.net_to_owner == Decimal("1400.00")


# --- Exemption ---------------------------------------------------------------


def test_gross_tax_exempt_skips_tax(property_: Property, gbp: Currency, rule: RateBand) -> None:
    _finance(property_, tax_is_exempt=True)

    quote = _quote(property_, gbp)

    assert quote.tax == Decimal("0.00")
    assert quote.commission == Decimal("210.00")  # (1400 - 0) x 15%
    assert quote.total == Decimal("1400.00")
    assert quote.net_to_owner == Decimal("1190.00")


def test_net_tax_exempt_with_fixed_commission(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    _finance(
        property_,
        commission_type=CommissionCalcType.FIXED,
        commission_amount="100",
        tax_is_exempt=True,
    )
    _set_basis(rule.period.plan, PriceBasis.NET)

    quote = _quote(property_, gbp)

    assert quote.tax == Decimal("0.00")
    assert quote.commission == Decimal("100.00")
    assert quote.total == Decimal("1500.00")
    assert quote.net_to_owner == Decimal("1400.00")


# --- Guards (deliberate divergence from legacy — sanitise, don't 500) --------


def test_net_commission_pct_at_100_sanitised_to_zero(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """A ≥100% NET gross-up would divide by ≤0 — sanitise commission to 0.00."""
    _finance(property_, commission_amount="100")
    _set_basis(rule.period.plan, PriceBasis.NET)

    quote = _quote(property_, gbp)

    assert quote.commission == Decimal("0.00")
    assert quote.tax == Decimal("155.56")  # 1400/0.9 - 1400
    assert quote.total == Decimal("1555.56")


def test_net_tax_rate_at_100_sanitised_to_zero(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    _finance(property_, tax_percentage="100")
    _set_basis(rule.period.plan, PriceBasis.NET)

    quote = _quote(property_, gbp)

    assert quote.tax == Decimal("0.00")
    assert quote.commission == Decimal("247.06")
    assert quote.total == Decimal("1647.06")


def test_gross_tax_rate_at_or_above_100_sanitised_to_zero(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """A tax >= the gross would flip the commission base negative — sanitise."""
    _finance(property_, tax_percentage="110")

    quote = _quote(property_, gbp)

    assert quote.tax == Decimal("0.00")
    assert quote.commission == Decimal("210.00")  # (1400 - 0) x 15%
    assert quote.total == Decimal("1400.00")
    assert quote.net_to_owner == Decimal("1190.00")


def test_zero_base_after_full_discount_yields_zero_commission_and_tax(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    Discount.objects.create(
        property=property_,
        name="Comp stay",
        code="FREE100",
        rule_kind=RuleKind.PROMO_CODE,
        kind=DiscountKind.PERCENT,
        amount=Decimal("100.00"),
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        is_active=True,
    )
    _finance(property_)

    quote = _quote(property_, gbp, discount_code="FREE100")

    assert quote.commission == Decimal("0.00")
    assert quote.tax == Decimal("0.00")
    assert quote.total == Decimal("0.00")


# --- Non-commissionable extras (GAP-076) --------------------------------------


def _extra(
    property_: Property,
    gbp: Currency,
    *,
    name: str = "Chef",
    amount: str = "1000.00",
    commissionable: bool = False,
    is_mandatory: bool = True,
) -> Extra:
    return Extra.objects.create(
        property=property_,
        currency=gbp,
        name=name,
        kind=ExtraKind.OTHER,
        calc=ExtraCalc.FIXED_PER_STAY,
        is_mandatory=is_mandatory,
        amount=Decimal(amount),
        commissionable=commissionable,
        is_active=True,
    )


def test_gross_non_commissionable_extra_passes_through_to_owner(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """GROSS: the extra bills the guest but never enters commission/tax bases."""
    _finance(property_)  # 15% commission, 10% tax
    _extra(property_, gbp)

    quote = _quote(property_, gbp)

    assert quote.tax == Decimal("140.00")  # on 1400 only
    assert quote.commission == Decimal("189.00")  # (1400 - 140) x 15%
    assert quote.total == Decimal("2400.00")  # guest still pays the chef
    assert quote.net_to_owner == Decimal("2071.00")  # 1071 + 1000 pass-through
    assert quote.extras_total == Decimal("1000.00")
    assert quote.breakdown["commission_base"] == "1400.00"
    assert quote.breakdown["extras_non_commissionable_total"] == "1000.00"
    assert quote.breakdown["extras"][0]["commissionable"] is False


def test_net_non_commissionable_extra_passes_through_to_owner(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """NET: gross-up applies to the commissionable base only; extra rides on top."""
    _finance(property_)
    _set_basis(rule.period.plan, PriceBasis.NET)
    _extra(property_, gbp)

    quote = _quote(property_, gbp)

    assert quote.commission == Decimal("247.06")  # 1400/0.85 - 1400
    assert quote.tax == Decimal("183.01")
    assert quote.total == Decimal("2830.07")  # 1830.07 + 1000
    assert quote.net_to_owner == Decimal("2400.00")  # 1400 net + 1000 pass-through
    assert quote.breakdown["commission_base"] == "1400.00"
    assert quote.breakdown["extras_non_commissionable_total"] == "1000.00"


def test_mixed_extras_split_between_bases(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """Commissionable extras fold into the base; non-commissionable ride on top."""
    _finance(property_)
    _extra(property_, gbp, name="Cleaning", amount="150.00", commissionable=True)
    _extra(property_, gbp)

    quote = _quote(property_, gbp)

    # commission base = 1400 + 150 = 1550
    assert quote.tax == Decimal("155.00")
    assert quote.commission == Decimal("209.25")  # (1550 - 155) x 15%
    assert quote.total == Decimal("2550.00")
    assert quote.net_to_owner == Decimal("2185.75")
    assert quote.extras_total == Decimal("1150.00")  # full guest-facing sum
    assert quote.breakdown["commission_base"] == "1550.00"
    assert quote.breakdown["extras_non_commissionable_total"] == "1000.00"


def test_percent_discount_computes_on_commissionable_subtotal_only(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """A percent discount never discounts the pass-through extra (GAP-076)."""
    _finance(property_)
    _extra(property_, gbp, name="Cleaning", amount="150.00", commissionable=True)
    _extra(property_, gbp)
    Discount.objects.create(
        property=property_,
        name="Promo",
        code="TEN",
        rule_kind=RuleKind.PROMO_CODE,
        kind=DiscountKind.PERCENT,
        amount=Decimal("10.00"),
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        is_active=True,
    )

    quote = _quote(property_, gbp, discount_code="TEN")

    # discount = 10% x (1400 + 150) = 155, NOT 10% x 2550 = 255
    assert quote.discount == Decimal("155.00")
    # commission base = 1400 + 150 - 155 = 1395
    assert quote.tax == Decimal("139.50")
    # (1395 - 139.50) x 15% = 188.325 → 188.32 (banker's rounding, GAP-035 pin)
    assert quote.commission == Decimal("188.32")
    assert quote.total == Decimal("2395.00")
    assert quote.net_to_owner == Decimal("2067.18")
    assert quote.breakdown["commission_base"] == "1395.00"


def test_zero_commissionable_base_still_bills_non_commissionable_extra(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """Guard pin: comped stay + pass-through extra → no commission/tax, extra survives."""
    _finance(property_)
    _extra(property_, gbp)
    Discount.objects.create(
        property=property_,
        name="Comp stay",
        code="FREE100",
        rule_kind=RuleKind.PROMO_CODE,
        kind=DiscountKind.PERCENT,
        amount=Decimal("100.00"),
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        is_active=True,
    )

    quote = _quote(property_, gbp, discount_code="FREE100")

    assert quote.commission == Decimal("0.00")
    assert quote.tax == Decimal("0.00")
    assert quote.total == Decimal("1000.00")
    assert quote.net_to_owner == Decimal("1000.00")
    assert quote.breakdown["commission_base"] == "0.00"


def test_over_discount_erodes_pass_through_extra_not_guest_total(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """Deliberate pin: a discount beyond the commissionable subtotal drives the
    base negative and nets against the pass-through extra — the guest total is
    IDENTICAL to the pre-GAP-076 fold for the same inputs (customer-facing money
    never moves), so the erosion lands on the owner side, not the guest's bill.
    """
    _finance(property_)
    _extra(property_, gbp)  # non-commissionable 1000
    Discount.objects.create(
        property=property_,
        name="Mega promo",
        code="MEGA",
        rule_kind=RuleKind.PROMO_CODE,
        kind=DiscountKind.FIXED,
        amount=Decimal("2000.00"),
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        is_active=True,
    )

    quote = _quote(property_, gbp, discount_code="MEGA")

    assert quote.commission == Decimal("0.00")  # base <= 0 guard
    assert quote.tax == Decimal("0.00")
    assert quote.total == Decimal("400.00")  # 1400 + 1000 - 2000, as before GAP-076
    assert quote.net_to_owner == Decimal("400.00")
    assert quote.breakdown["commission_base"] == "-600.00"  # recorded truthfully


def test_opt_in_non_commissionable_extra_passes_through(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """A non-mandatory non-commissionable extra behaves the same once opted in."""
    _finance(property_)
    optional = _extra(property_, gbp, is_mandatory=False)

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        party=4,
        currency=gbp,
        opt_in_extras=[optional.pk],
    )

    assert quote.commission == Decimal("189.00")
    assert quote.total == Decimal("2400.00")
    assert quote.net_to_owner == Decimal("2071.00")


def test_tax_exempt_with_non_commissionable_extra(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    _finance(property_, tax_is_exempt=True)
    _extra(property_, gbp)

    quote = _quote(property_, gbp)

    assert quote.tax == Decimal("0.00")
    assert quote.commission == Decimal("210.00")  # (1400 - 0) x 15%
    assert quote.total == Decimal("2400.00")
    assert quote.net_to_owner == Decimal("2190.00")


def test_commissionable_extras_keep_existing_snapshot_shape(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """Regression: default-flag extras reproduce the old maths; new keys are sane."""
    _finance(property_)
    _extra(property_, gbp, name="Cleaning", amount="150.00", commissionable=True)

    quote = _quote(property_, gbp)

    # Identical to the old base = 1400 + 150 fold.
    assert quote.tax == Decimal("155.00")
    assert quote.commission == Decimal("209.25")
    assert quote.total == Decimal("1550.00")
    assert quote.net_to_owner == Decimal("1185.75")
    assert quote.breakdown["commission_base"] == "1550.00"
    assert quote.breakdown["extras_non_commissionable_total"] == "0.00"
    assert quote.breakdown["extras"][0]["commissionable"] is True


# --- GAP-079 — commission after local VAT (worked example) -------------------
#
# Confirms the ordering Nick described (2026-07-08 call): local VAT (13%)
# comes off the gross FIRST, then commission off the remainder. This is the
# GROSS branch's existing behaviour, matching legacy `RatesModel.Calculate()`;
# ordering is a function of `price_basis` alone — no per-villa toggle.
# Constructed example (13% VAT, 20% commission, 10,000 gross week); to be
# re-reconciled against a real villa statement when Nick provides one.
# COMMISSIONABLE extras fold into the VAT base (pinned above by
# `test_gross_extras_and_discount_fold_into_base`); non-commissionable extras
# are excluded from BOTH bases — full pass-through (GAP-076, pinned above).

_GAP079_CHECKOUT = date(2026, 6, 18)  # 8 nights from 10 Jun


def _gap079_band(period: RatePeriod) -> RateBand:
    """1,250.00/night so the 8-night stay yields an exact 10,000.00 base.

    (10,000 over the shared 7-night `rule` fixture is unrepresentable — the
    weekly rate derives via a per-night 0.01 quantize, landing on 9,999.99.)
    """
    return RateBand.objects.create(
        period=period,
        min_party=1,
        max_party=8,
        nightly=Decimal("1250.00"),
    )


def test_gap079_gross_takes_commission_after_local_vat(
    property_: Property, gbp: Currency, period: RatePeriod
) -> None:
    """13% VAT off the gross first, then 20% commission off the remainder."""
    _finance(property_, commission_amount="20", tax_percentage="13")
    _gap079_band(period)

    quote = _quote(property_, gbp, date_to=_GAP079_CHECKOUT)

    assert quote.rate_subtotal == Decimal("10000.00")
    assert quote.tax == Decimal("1300.00")  # 10,000 x 13% — VAT first
    assert quote.commission == Decimal("1740.00")  # (10,000 - 1,300) x 20%
    assert quote.total == Decimal("10000.00")  # guest still pays the gross
    assert quote.net_to_owner == Decimal("6960.00")  # 10,000 - 1,300 - 1,740


def test_gap079_net_grosses_up_commission_then_vat(
    property_: Property, gbp: Currency, period: RatePeriod
) -> None:
    """NET reverses the ordering (legacy parity): commission grosses up off
    the net first, then VAT on (net + commission)."""
    _finance(property_, commission_amount="20", tax_percentage="13")
    band = _gap079_band(period)
    _set_basis(band.period.plan, PriceBasis.NET)

    quote = _quote(property_, gbp, date_to=_GAP079_CHECKOUT)

    assert quote.commission == Decimal("2500.00")  # 10,000/0.8 - 10,000
    assert quote.tax == Decimal("1867.82")  # 12,500/0.87 - 12,500
    assert quote.total == Decimal("14367.82")
    assert quote.net_to_owner == Decimal("10000.00")


# --- Projection carries the basis --------------------------------------------


def test_projected_quote_inherits_net_basis_from_anchor(
    property_: Property, gbp: Currency, rule: RateBand
) -> None:
    """A projected year prices with the anchor plan's basis (projection.py)."""
    _finance(property_)
    _set_basis(rule.period.plan, PriceBasis.NET)

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2028, 6, 10),
        date_to=date(2028, 6, 17),
        party=4,
        currency=gbp,
    )

    assert quote.is_projected is True
    assert quote.rate_subtotal == Decimal("1400.00")
    assert quote.commission == Decimal("247.06")
    assert quote.tax == Decimal("183.01")
    assert quote.total == Decimal("1830.07")
    assert quote.net_to_owner == Decimal("1400.00")
