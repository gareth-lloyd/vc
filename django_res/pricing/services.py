"""Stateless pricing services.

This module is the public surface of the pricing app for the rest of the
system. It deliberately contains *no* DB writes — only reads — so that
quote computation is a pure function of the inputs and the rate / extra /
discount catalogue rows at the time of the call.

Public surface:
- `PricingEngine.quote(...)` — compute a `Quote` for a stay.
- `FxConverter.convert(...)` — convert money using the latest FxRate ≤ as_of.
- `AvailabilityService` — skeleton; real impl lands with reservations.Booking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db.models import Q

from core.exceptions import (
    ChangeoverViolation,
    DiscountNotApplicable,
    MinNightsNotMet,
    NoRateAvailable,
    PartyOutOfRange,
)
from pricing.enums import DiscountKind, ExtraCalc, RuleKind
from pricing.models import (
    Currency,
    Discount,
    Extra,
    FxRate,
    RateCard,
    RatePlan,
    RateRule,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class QuoteLine:
    """A single-night rate line in a quote breakdown."""

    date: date
    rule_id: int
    card_id: int
    nightly: Decimal
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "rule_id": self.rule_id,
            "card_id": self.card_id,
            "nightly": str(self.nightly),
            "notes": self.notes,
        }


@dataclass
class AppliedExtra:
    """An Extra row that was applied at quote time, plus its computed amount."""

    extra_id: int
    name: str
    kind: str
    calc: str
    computed_amount: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "extra_id": self.extra_id,
            "name": self.name,
            "kind": self.kind,
            "calc": self.calc,
            "computed_amount": str(self.computed_amount),
        }


@dataclass
class Quote:
    """Result of `PricingEngine.quote()`. The `breakdown` is JSON-snapshotable."""

    property_id: int
    currency_code: str
    party: int
    date_from: date
    date_to: date
    lines: list[QuoteLine]
    rate_subtotal: Decimal
    extras: list[AppliedExtra]
    extras_total: Decimal
    discount: Decimal
    commission: Decimal
    tax: Decimal
    total: Decimal
    breakdown: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# FX conversion
# ---------------------------------------------------------------------------


class FxConverter:
    """Convert money amounts via the most recent `FxRate` ≤ `as_of`."""

    @classmethod
    def convert(
        cls,
        amount: Decimal,
        from_ccy: Currency,
        to_ccy: Currency,
        as_of: date | None = None,
    ) -> Decimal:
        if from_ccy.pk == to_ccy.pk:
            return amount
        cutoff = as_of or date.today()
        rate = (
            FxRate.objects.filter(base=from_ccy, quote=to_ccy, as_of__lte=cutoff)
            .order_by("-as_of")
            .first()
        )
        if rate is None:
            raise NoRateAvailable(
                f"No FxRate available for {from_ccy.code}->{to_ccy.code} on/before {cutoff}"
            )
        return (amount * rate.rate).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Availability skeleton
# ---------------------------------------------------------------------------


@dataclass
class Conflict:
    """A reason why a date range is not bookable."""

    kind: str
    date_from: date
    date_to: date
    detail: str = ""


@dataclass
class CellStatus:
    """Per-day cell on the admin availability grid."""

    available: bool
    reason: str = ""


class AvailabilityService:
    """Availability queries — full implementation depends on `reservations.Booking`.

    Lives here (not `reservations`) because the engine consults change-over
    rules at quote time. For now `is_available` returns True and `conflicts`
    returns []; once `reservations.Booking` and `reservations.BookingHold`
    exist, those models' EXCLUDE constraints provide the real backing query.
    """

    @classmethod
    def is_available(
        cls,
        property: Any,
        date_from: date,
        date_to: date,
        *,
        ignore_hold_ids: Iterable[int] | None = None,
    ) -> bool:
        # TODO: once reservations.Booking + BookingHold exist, query them here:
        #   - no overlapping active Booking
        #   - no live BookingHold (released_at IS NULL AND expires_at > now)
        #     except ones in ignore_hold_ids
        #   - check-in weekday matches properties.ChangeOverRule for the window
        #   - stay length ≥ PropertySettings.effective min_nights_rental
        return True

    @classmethod
    def conflicts(
        cls,
        property: Any,
        date_from: date,
        date_to: date,
    ) -> list[Conflict]:
        # TODO: enumerate active Booking + live BookingHold rows that overlap.
        return []

    @classmethod
    def calendar(
        cls,
        property: Any,
        range_start: date,
        range_end: date,
    ) -> dict[date, CellStatus]:
        # TODO: build a {date: CellStatus} grid from Booking + BookingHold + ChangeOverRule.
        result: dict[date, CellStatus] = {}
        cursor = range_start
        while cursor <= range_end:
            result[cursor] = CellStatus(available=True)
            cursor += timedelta(days=1)
        return result


# ---------------------------------------------------------------------------
# Pricing engine
# ---------------------------------------------------------------------------


def _nights(date_from: date, date_to: date) -> list[date]:
    """Inclusive-exclusive nights: [date_from, date_to) — date_to is checkout."""
    if date_to <= date_from:
        return []
    out: list[date] = []
    cursor = date_from
    while cursor < date_to:
        out.append(cursor)
        cursor += timedelta(days=1)
    return out


def _rule_nightly(rule: RateRule) -> Decimal:
    """Return the effective nightly rate for a rule, deriving from weekly if needed."""
    if rule.nightly is not None:
        return Decimal(rule.nightly)
    if rule.weekly is not None:
        # Weekly / 7 — quantize to 2dp.
        return (Decimal(rule.weekly) / Decimal(7)).quantize(Decimal("0.01"))
    # POA: caller should never reach the price step on a POA rule, but be
    # defensive.
    raise NoRateAvailable(f"RateRule {rule.pk} is POA and cannot be priced")


def _rule_specificity(rule: RateRule) -> int:
    """Days in `rule`'s date range — narrower wins on priority ties."""
    return (rule.date_to - rule.date_from).days


def _pick_rule_for_night(
    cards: list[RateCard],
    rules_by_card: dict[int, list[RateRule]],
    night: date,
    party: int,
) -> tuple[RateCard, RateRule] | None:
    """Pick the highest-priority rule covering `night` and `party` across cards.

    Tie-break order (per 04-pricing.md §Services step 2):
    1. Higher `priority` wins.
    2. Narrower date range wins (most-specific match).
    3. Lower `card.sort_order` wins (cross-card tie-break).
    4. Higher `rule.id` wins (deterministic fallback).
    """
    best: tuple[RateCard, RateRule] | None = None
    best_key: tuple[int, int, int, int] | None = None
    for card in cards:
        for rule in rules_by_card.get(card.pk, []):
            if not (rule.date_from <= night <= rule.date_to):
                continue
            if not (rule.min_party <= party <= rule.max_party):
                continue
            # Sort key: maximise priority, minimise specificity, minimise sort_order, maximise id.
            key = (
                int(rule.priority),
                -_rule_specificity(rule),
                -int(card.sort_order),
                int(rule.pk),
            )
            if best_key is None or key > best_key:
                best_key = key
                best = (card, rule)
    return best


def _calc_extra(
    extra: Extra,
    *,
    nights: int,
    party: int,
    rate_subtotal: Decimal,
) -> Decimal:
    """Compute the per-quote contribution of an Extra based on its `calc`."""
    amount = Decimal(extra.amount)
    if extra.calc == ExtraCalc.FIXED_PER_STAY:
        return amount
    if extra.calc == ExtraCalc.FIXED_PER_NIGHT:
        return (amount * nights).quantize(Decimal("0.01"))
    if extra.calc == ExtraCalc.FIXED_PER_PERSON:
        return (amount * party).quantize(Decimal("0.01"))
    if extra.calc == ExtraCalc.FIXED_PER_PERSON_PER_NIGHT:
        return (amount * nights * party).quantize(Decimal("0.01"))
    if extra.calc == ExtraCalc.PERCENT_OF_SUBTOTAL:
        return (rate_subtotal * amount / Decimal(100)).quantize(Decimal("0.01"))
    raise ValueError(f"Unknown Extra.calc: {extra.calc!r}")


def _date_ranges_overlap(
    a_from: date,
    a_to: date,
    b_from: date | None,
    b_to: date | None,
) -> bool:
    """True if [a_from, a_to] intersects [b_from, b_to]; null bounds = open-ended."""
    if b_from is not None and a_to < b_from:
        return False
    return not (b_to is not None and a_from > b_to)


def _apply_discount(
    discount: Discount,
    *,
    subtotal: Decimal,
) -> Decimal:
    """Return the discount value to subtract from the subtotal."""
    if discount.kind == DiscountKind.PERCENT:
        return (subtotal * Decimal(discount.amount) / Decimal(100)).quantize(Decimal("0.01"))
    if discount.kind == DiscountKind.FIXED:
        return Decimal(discount.amount).quantize(Decimal("0.01"))
    raise ValueError(f"Unknown Discount.kind: {discount.kind!r}")


class PricingEngine:
    """Stateless engine that turns (property, dates, party, currency) into a Quote."""

    @classmethod
    def quote(
        cls,
        *,
        property: Any,
        date_from: date,
        date_to: date,
        party: int,
        currency: Currency,
        discount_code: str | None = None,
        opt_in_extras: list[int] | None = None,
        as_of: date | None = None,
    ) -> Quote:
        if date_to <= date_from:
            raise NoRateAvailable("date_to must be strictly after date_from")
        if party <= 0:
            raise PartyOutOfRange("party must be a positive integer")

        nights = _nights(date_from, date_to)
        as_of = as_of or date.today()

        # ----- Step 1: resolve RatePlan -----
        plan = cls._resolve_plan(property, currency, date_from, date_to)

        # ----- Step 2: collect cards and approved rules -----
        cards = list(
            RateCard.objects.filter(plan=plan, is_active=True).order_by("sort_order", "pk")
        )
        if not cards:
            raise NoRateAvailable(
                f"No active RateCard on plan {plan.pk} for {date_from}..{date_to}"
            )

        rules_by_card: dict[int, list[RateRule]] = {}
        for rule in RateRule.objects.filter(card__in=cards, is_approved=True):
            rules_by_card.setdefault(rule.card_id, []).append(rule)

        # ----- Pick winning rule per night -----
        lines: list[QuoteLine] = []
        chosen_cards: dict[int, RateCard] = {}
        for night in nights:
            pick = _pick_rule_for_night(cards, rules_by_card, night, party)
            if pick is None:
                raise NoRateAvailable(
                    f"No approved RateRule on plan {plan.pk} for {night} party={party}"
                )
            card, rule = pick
            if rule.is_poa:
                raise NoRateAvailable(
                    f"RateRule {rule.pk} is POA — cannot generate automatic quote"
                )
            nightly = _rule_nightly(rule)
            lines.append(
                QuoteLine(
                    date=night,
                    rule_id=rule.pk,
                    card_id=card.pk,
                    nightly=nightly,
                )
            )
            chosen_cards[card.pk] = card

        # ----- Validate the winning card(s) constraints -----
        # The "winning" card overall is the one whose rule had the highest priority.
        # Per the spec, validate min_nights / max_nights / changeover_weekday
        # against the *winning* card. Where multiple cards contributed lines,
        # take the card of the line with the strictest min_nights / earliest
        # date — for simplicity (and matching the spec language) we pick the
        # card of the first line.
        winning_card = chosen_cards[lines[0].card_id]
        cls._validate_card_against_stay(
            winning_card,
            date_from=date_from,
            date_to=date_to,
            nights=len(nights),
        )

        # ----- Step 4: rate subtotal -----
        rate_subtotal = sum((ln.nightly for ln in lines), Decimal("0")).quantize(Decimal("0.01"))

        # ----- Step 5: mandatory extras -----
        extras_applied: list[AppliedExtra] = []
        extras_qs = Extra.objects.filter(
            property=property,
            is_active=True,
            currency=currency,
        )
        mandatory = [e for e in extras_qs.filter(is_mandatory=True)]
        opt_in_ids = set(opt_in_extras or [])
        opt_in = [e for e in extras_qs.filter(is_mandatory=False, pk__in=opt_in_ids)]

        for extra in (*mandatory, *opt_in):
            if not _date_ranges_overlap(date_from, date_to, extra.applies_from, extra.applies_to):
                continue
            if extra.min_party is not None and party < extra.min_party:
                continue
            if extra.max_party is not None and party > extra.max_party:
                continue
            computed = _calc_extra(
                extra,
                nights=len(nights),
                party=party,
                rate_subtotal=rate_subtotal,
            )
            extras_applied.append(
                AppliedExtra(
                    extra_id=extra.pk,
                    name=extra.name,
                    kind=extra.kind,
                    calc=extra.calc,
                    computed_amount=computed,
                )
            )

        extras_total = sum((ax.computed_amount for ax in extras_applied), Decimal("0")).quantize(
            Decimal("0.01")
        )

        # ----- Step 7: discounts -----
        discount_total = cls._apply_discounts(
            property=property,
            card=winning_card,
            subtotal=rate_subtotal + extras_total,
            party=party,
            date_from=date_from,
            date_to=date_to,
            nights=len(nights),
            as_of=as_of,
            discount_code=discount_code,
        )

        # ----- Steps 8-9: commission and tax -----
        # Commission and tax depend on PropertyFinance — owned by the
        # properties app. If the property has a `finance` attribute with
        # `effective_commission` / `effective_tax_policy`, use them; otherwise
        # default to zero so the engine remains testable in isolation.
        commission = cls._compute_commission(
            property=property,
            base=rate_subtotal + extras_total - discount_total,
            as_of=as_of,
        )
        tax = cls._compute_tax(
            property=property,
            base=rate_subtotal + extras_total - discount_total,
            as_of=as_of,
        )

        total = (rate_subtotal + extras_total - discount_total + commission + tax).quantize(
            Decimal("0.01")
        )

        breakdown: dict[str, Any] = {
            "property_id": getattr(property, "pk", None),
            "currency_code": currency.code,
            "party": party,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "lines": [ln.to_dict() for ln in lines],
            "rate_subtotal": str(rate_subtotal),
            "extras": [ax.to_dict() for ax in extras_applied],
            "extras_total": str(extras_total),
            "discount": str(discount_total),
            "commission": str(commission),
            "tax": str(tax),
            "total": str(total),
            "plan_id": plan.pk,
            "winning_card_id": winning_card.pk,
        }

        return Quote(
            property_id=getattr(property, "pk", 0) or 0,
            currency_code=currency.code,
            party=party,
            date_from=date_from,
            date_to=date_to,
            lines=lines,
            rate_subtotal=rate_subtotal,
            extras=extras_applied,
            extras_total=extras_total,
            discount=discount_total,
            commission=commission,
            tax=tax,
            total=total,
            breakdown=breakdown,
        )

    # ------------------------------------------------------------------
    # Step helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_plan(
        property: Any,
        currency: Currency,
        date_from: date,
        date_to: date,
    ) -> RatePlan:
        candidates = (
            RatePlan.objects.filter(
                property=property,
                currency=currency,
                is_active=True,
                effective_from__lte=date_from,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=date_to))
            .order_by("-effective_from", "-pk")
        )
        plan = candidates.first()
        if plan is None:
            raise NoRateAvailable(
                f"No active RatePlan for property {getattr(property, 'pk', '?')} "
                f"currency {currency.code} covering {date_from}..{date_to}"
            )
        return plan

    @staticmethod
    def _validate_card_against_stay(
        card: RateCard,
        *,
        date_from: date,
        date_to: date,
        nights: int,
    ) -> None:
        if nights < card.min_nights:
            raise MinNightsNotMet(
                f"RateCard {card.pk} requires min_nights={card.min_nights}, got {nights}"
            )
        if card.max_nights is not None and nights > card.max_nights:
            raise MinNightsNotMet(
                f"RateCard {card.pk} caps max_nights={card.max_nights}, got {nights}"
            )
        if card.changeover_weekday is not None and date_from.weekday() != card.changeover_weekday:
            raise ChangeoverViolation(
                f"RateCard {card.pk} requires changeover on weekday "
                f"{card.changeover_weekday}, got {date_from.weekday()}"
            )

    @staticmethod
    def _apply_discounts(
        *,
        property: Any,
        card: RateCard,
        subtotal: Decimal,
        party: int,
        date_from: date,
        date_to: date,
        nights: int,
        as_of: date,
        discount_code: str | None,
    ) -> Decimal:
        qs = Discount.objects.filter(
            is_active=True,
            valid_from__lte=date_from,
            valid_to__gte=date_from,
        ).filter(Q(card=card) | Q(card__isnull=True, property=property))

        applied_total = Decimal("0")
        for d in qs:
            # Skip max_uses cap.
            if d.max_uses is not None and d.uses_count >= d.max_uses:
                continue
            # min_nights gate.
            if nights < d.min_nights:
                continue
            # Promo codes only apply when the caller supplied a matching code.
            if d.rule_kind == RuleKind.PROMO_CODE:
                if discount_code is None or d.code != discount_code:
                    continue
            else:
                # Auto-apply rule kinds: LENGTH_OF_STAY (already filtered by
                # min_nights), EARLY_BIRD / LAST_MINUTE (threshold_days from
                # as_of), REPEAT_GUEST (skipped until reservations exists).
                if d.rule_kind == RuleKind.EARLY_BIRD and d.threshold_days is not None:
                    if (date_from - as_of).days < d.threshold_days:
                        continue
                if d.rule_kind == RuleKind.LAST_MINUTE and d.threshold_days is not None:
                    if (date_from - as_of).days > d.threshold_days:
                        continue
                if d.rule_kind == RuleKind.REPEAT_GUEST:
                    # TODO: requires reservations integration; skip for now.
                    continue
            applied_total += _apply_discount(d, subtotal=subtotal)

        # If the caller passed a discount_code that didn't match any active
        # discount, surface a typed error so the UX can show "code not valid".
        if discount_code is not None:
            matched = qs.filter(code=discount_code, rule_kind=RuleKind.PROMO_CODE).exists()
            if not matched:
                raise DiscountNotApplicable(
                    f"Promo code {discount_code!r} did not match any active discount"
                )

        return applied_total.quantize(Decimal("0.01"))

    @staticmethod
    def _compute_commission(
        *,
        property: Any,
        base: Decimal,
        as_of: date,
    ) -> Decimal:
        finance = getattr(property, "finance", None)
        if finance is None:
            return Decimal("0.00")
        resolver = getattr(finance, "effective_commission", None)
        if resolver is None:
            return Decimal("0.00")
        commission = resolver(as_of=as_of)
        if commission is None:
            return Decimal("0.00")
        # Expect a Decimal percentage; fall back to multiplying directly if a flat amount.
        return (base * Decimal(commission) / Decimal(100)).quantize(Decimal("0.01"))

    @staticmethod
    def _compute_tax(
        *,
        property: Any,
        base: Decimal,
        as_of: date,
    ) -> Decimal:
        finance = getattr(property, "finance", None)
        if finance is None:
            return Decimal("0.00")
        resolver = getattr(finance, "effective_tax_policy", None)
        if resolver is None:
            return Decimal("0.00")
        policy = resolver(as_of=as_of)
        if policy is None:
            return Decimal("0.00")
        rate = getattr(policy, "rate", None)
        if rate is None:
            return Decimal("0.00")
        return (base * Decimal(rate) / Decimal(100)).quantize(Decimal("0.01"))
