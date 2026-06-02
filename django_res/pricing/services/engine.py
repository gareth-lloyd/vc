"""Stateless pricing engine.

Public surface: `PricingEngine.quote(...)` — compute a `Quote` for a stay.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Q

from core.exceptions import (
    DiscountNotApplicable,
    MinNightsNotMet,
    NoRateAvailable,
    PartyOutOfRange,
)
from pricing.enums import RuleKind
from pricing.models import (
    Currency,
    Discount,
    Extra,
    RateCard,
    RatePlan,
    RateRule,
)
from pricing.services.discounts import apply_discount
from pricing.services.extras import calc_extra, date_ranges_overlap
from pricing.services.projection import PricingContext, RateProjectionService
from pricing.services.quote import AppliedExtra, Quote, QuoteLine
from pricing.services.rates import (
    NoCoverage,
    OutOfRange,
    Picked,
    nights,
    pick_rule_for_night,
    rule_nightly,
)
from properties.services.changeover import ChangeoverService


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
        allow_projection: bool = True,
    ) -> Quote:
        if date_to <= date_from:
            raise NoRateAvailable("date_to must be strictly after date_from")
        if party <= 0:
            raise PartyOutOfRange("party must be a positive integer")

        as_of = as_of or date.today()

        # Resolve a real plan covering the stay; when none does (a year with no
        # rate card) fall through to a lazily-derived guide rate projected from
        # the most recent year that has rates. `allow_projection=False` forces the
        # hard `NoRateAvailable` for callers that must not price on a guide (e.g. a
        # booking-time guard). See `04-pricing.md` "Projected pricing for future
        # years".
        context = cls._load_real_context(property, currency, date_from, date_to)
        if context is None and allow_projection:
            context = RateProjectionService.project(
                property=property,
                date_from=date_from,
                date_to=date_to,
                currency=currency,
            )
        if context is None:
            raise NoRateAvailable(
                f"No active RatePlan for property {getattr(property, 'pk', '?')} "
                f"currency {currency.code} covering {date_from}..{date_to}"
            )
        plan = context.plan
        cards = context.cards
        rules_by_card = context.rules_by_card

        # Changeover auto-shift (GAP-007): legacy nudged a non-conforming
        # arrival forward to the next valid changeover day rather than
        # rejecting it. The property's effective changeover day (a
        # ChangeOverRule window, else the settings chain) is the single source
        # of truth; `any` / unconstrained means no shift.
        property_weekday = ChangeoverService.required_weekday(property, date_from)
        allowed_weekdays = {property_weekday} if property_weekday is not None else set()
        date_from, date_to, changeover_shifted_from = ChangeoverService.align_forward(
            allowed_weekdays, date_from, date_to
        )

        stay_nights = nights(date_from, date_to)

        lines: list[QuoteLine] = []
        chosen_cards: dict[int, RateCard] = {}
        for night in stay_nights:
            # Distinguish "no rule for this night at all" from "rules exist
            # for this night but none match the party size". The legacy
            # stored-proc defaulted to the highest bracket when party fell
            # outside every band; the rebuild raises `PartyOutOfRange`
            # instead (see `09-departures.md` bug #2). The tagged result
            # carries the disambiguation out of `pick_rule_for_night`'s
            # single pass, so the engine doesn't have to re-walk the grid.
            pick = pick_rule_for_night(cards, rules_by_card, night, party)
            if isinstance(pick, OutOfRange):
                raise PartyOutOfRange(
                    f"party={party} matches no RateRule bracket on plan {plan.pk} for {night}"
                )
            if isinstance(pick, NoCoverage):
                # Legacy quietly priced an uncovered night at the villa's
                # setting price (ResService.cs:2150-2160). The rebuild
                # reinstates that leniency only when the plan opts in via
                # `fallback_nightly`; otherwise it raises as before. Note
                # `OutOfRange` above still raises — a fallback must never mask
                # a party-bracket miss (see SMELL-007 / GAP-008).
                if plan.fallback_nightly is not None:
                    lines.append(
                        QuoteLine(
                            date=night,
                            rule_id=None,
                            card_id=None,
                            nightly=Decimal(plan.fallback_nightly),
                        )
                    )
                    continue
                raise NoRateAvailable(
                    f"No approved RateRule on plan {plan.pk} for {night} party={party}"
                )
            assert isinstance(pick, Picked)  # narrowing for mypy
            card, rule = pick.card, pick.rule
            if rule.is_poa:
                raise NoRateAvailable(
                    f"RateRule {rule.pk} is POA — cannot generate automatic quote"
                )
            nightly = rule_nightly(rule)
            lines.append(
                QuoteLine(
                    date=night,
                    rule_id=rule.pk,
                    card_id=card.pk,
                    nightly=nightly,
                )
            )
            chosen_cards[card.pk] = card

        # The winning card is the one priced for the first real (non-fallback)
        # night. An all-fallback stay has no card to validate — mirror legacy,
        # which had no card concept on the fallback path, and skip the check.
        winning_card = next(
            (chosen_cards[ln.card_id] for ln in lines if ln.card_id is not None),
            None,
        )
        if winning_card is not None:
            cls._validate_card_against_stay(winning_card, nights=len(stay_nights))

        rate_subtotal = sum((ln.nightly for ln in lines), Decimal("0")).quantize(Decimal("0.01"))

        extras_applied: list[AppliedExtra] = []
        opt_in_ids = set(opt_in_extras or [])
        all_extras = list(
            Extra.objects.filter(property=property, is_active=True, currency=currency)
        )
        applicable_extras = [
            e for e in all_extras if e.is_mandatory or (not e.is_mandatory and e.pk in opt_in_ids)
        ]

        for extra in applicable_extras:
            if not date_ranges_overlap(date_from, date_to, extra.applies_from, extra.applies_to):
                continue
            if extra.min_party is not None and party < extra.min_party:
                continue
            if extra.max_party is not None and party > extra.max_party:
                continue
            computed = calc_extra(
                extra,
                nights=len(stay_nights),
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

        discount_total = cls._apply_discounts(
            property=property,
            card=winning_card,
            subtotal=rate_subtotal + extras_total,
            party=party,
            date_from=date_from,
            date_to=date_to,
            nights=len(stay_nights),
            as_of=as_of,
            discount_code=discount_code,
        )

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
        # Owner-net is captured at quote-time so downstream consumers (the
        # booking detail serializer, owner statements) never have to re-derive
        # it from the breakdown. See `09-departures.md`: serializers should
        # not subtract money.
        net_to_owner = (total - commission - tax).quantize(Decimal("0.01"))

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
            "net_to_owner": str(net_to_owner),
            "plan_id": plan.pk,
            "winning_card_id": winning_card.pk if winning_card is not None else None,
            "changeover_shifted_from": (
                changeover_shifted_from.isoformat() if changeover_shifted_from is not None else None
            ),
            # A projected quote is a guide rate carried from a prior year; the
            # provenance lets the quotation generator / email render the "rates
            # carried over — inquire for accurate rate" marker and is persisted
            # into the booking snapshot.
            "is_projected": context.is_projected,
            "projection": context.projection,
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
            net_to_owner=net_to_owner,
            changeover_shifted_from=changeover_shifted_from,
            is_projected=context.is_projected,
            breakdown=breakdown,
        )

    @staticmethod
    def _load_real_context(
        property: Any,
        currency: Currency,
        date_from: date,
        date_to: date,
    ) -> PricingContext | None:
        """Load the (plan, cards, rules) triple from a real plan covering the stay.

        Returns `None` when no active plan covers the whole `[date_from, date_to)`
        range — the signal for the caller to try a projection. A plan that *does*
        cover the dates but has no active cards is a misconfiguration, not a
        projection trigger, so it still raises `NoRateAvailable`.
        """
        plan = (
            RatePlan.objects.filter(
                property=property,
                currency=currency,
                is_active=True,
                effective_from__lte=date_from,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=date_to))
            .order_by("-effective_from", "-pk")
            .first()
        )
        if plan is None:
            return None
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
        return PricingContext(plan=plan, cards=cards, rules_by_card=rules_by_card)

    @staticmethod
    def _validate_card_against_stay(card: RateCard, *, nights: int) -> None:
        if nights < card.min_nights:
            raise MinNightsNotMet(
                f"RateCard {card.pk} requires min_nights={card.min_nights}, got {nights}"
            )
        if card.max_nights is not None and nights > card.max_nights:
            raise MinNightsNotMet(
                f"RateCard {card.pk} caps max_nights={card.max_nights}, got {nights}"
            )

    @staticmethod
    def _apply_discounts(
        *,
        property: Any,
        card: RateCard | None,
        subtotal: Decimal,
        party: int,
        date_from: date,
        date_to: date,
        nights: int,
        as_of: date,
        discount_code: str | None,
    ) -> Decimal:
        # Property-scoped card-less discounts always apply; this card's own
        # discounts apply only when a card actually won. On an all-fallback
        # stay `card is None` — guard the `Q(card=card)` disjunct, which would
        # otherwise collapse to `Q(card__isnull=True)` and leak every other
        # property's card-less discount into this quote.
        scope = Q(card__isnull=True, property=property)
        if card is not None:
            scope |= Q(card=card)
        qs = (
            Discount.objects.filter(
                is_active=True,
                valid_from__lte=date_from,
                valid_to__gte=date_from,
            )
            .filter(scope)
            # REPEAT_GUEST is recognised but unimplemented in v1 (no repeat-guest
            # detection exists yet — see GAP-009). Exclude it here so it can never
            # silently mis-apply; keep the enum member to avoid migration/API churn.
            .exclude(rule_kind=RuleKind.REPEAT_GUEST)
        )

        applied_total = Decimal("0")
        for d in qs:
            if d.max_uses is not None and d.uses_count >= d.max_uses:
                continue
            if nights < d.min_nights:
                continue
            if d.rule_kind == RuleKind.PROMO_CODE:
                if discount_code is None or d.code != discount_code:
                    continue
            else:
                if d.rule_kind == RuleKind.EARLY_BIRD and d.threshold_days is not None:
                    if (date_from - as_of).days < d.threshold_days:
                        continue
                if d.rule_kind == RuleKind.LAST_MINUTE and d.threshold_days is not None:
                    if (date_from - as_of).days > d.threshold_days:
                        continue
            applied_total += apply_discount(d, subtotal=subtotal)

        if discount_code is not None:
            matched = qs.filter(code=discount_code, rule_kind=RuleKind.PROMO_CODE).exists()
            if not matched:
                raise DiscountNotApplicable(
                    f"Promo code {discount_code!r} did not match any active discount"
                )

        return applied_total.quantize(Decimal("0.01"))

    @staticmethod
    def _call_finance_resolver(resolver: Any, as_of: date) -> Any:
        """Call a `PropertyFinance.effective_*` resolver tolerantly.

        The finance model's resolvers currently take no arguments and return
        dicts; the engine was written against a future `as_of=`/attribute
        shape. Support both so the two halves stay decoupled until the
        finance rewrite lands.

        TODO(finance-rewrite): delete this shim and the dict branches in
        `_compute_commission`/`_compute_tax` once `PropertyFinance.effective_*`
        accepts `as_of` and returns the scalar/attribute shape directly.
        """
        try:
            return resolver(as_of=as_of)
        except TypeError:
            return resolver()

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
        commission = PricingEngine._call_finance_resolver(resolver, as_of)
        if commission is None:
            return Decimal("0.00")
        if isinstance(commission, dict):
            # Only a percentage commission scales with the rate base; a fixed
            # commission is an owner-payout concern, not a guest-price line.
            if commission.get("calculation_type") != "percent":
                return Decimal("0.00")
            commission = commission.get("amount")
        if commission is None:
            return Decimal("0.00")
        return (base * Decimal(str(commission)) / Decimal(100)).quantize(Decimal("0.01"))

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
        policy = PricingEngine._call_finance_resolver(resolver, as_of)
        if policy is None:
            return Decimal("0.00")
        if isinstance(policy, dict):
            if policy.get("is_exempt"):
                return Decimal("0.00")
            rate = policy.get("percentage")
        else:
            rate = getattr(policy, "rate", None)
        if rate is None:
            return Decimal("0.00")
        return (base * Decimal(str(rate)) / Decimal(100)).quantize(Decimal("0.01"))
