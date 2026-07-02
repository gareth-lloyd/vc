"""Stateless pricing engine.

Public surface: `PricingEngine.quote(...)` — compute a `Quote` for a stay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from core.exceptions import (
    DiscountNotApplicable,
    MinNightsNotMet,
    NoRateAvailable,
    PartyOutOfRange,
)
from pricing.enums import PriceBasis, RuleKind
from pricing.models import (
    Currency,
    Discount,
    Extra,
    RateBand,
    RatePeriod,
    RatePlan,
)
from pricing.services.currency import pick_preferred_plan, resolve_property_currency
from pricing.services.discounts import apply_discount
from pricing.services.extras import calc_extra, date_ranges_overlap
from pricing.services.projection import PricingContext, RateProjectionService, keep_calendar_date
from pricing.services.quote import AppliedExtra, Quote, QuoteLine
from pricing.services.rates import (
    NoCoverage,
    OutOfRange,
    Picked,
    nights,
    pick_band_for_night,
    rule_nightly,
)
from properties.enums import CommissionCalcType
from properties.models.services import PropertyService
from properties.services.changeover import ChangeoverService


@dataclass(frozen=True)
class OccupancyBand:
    """A distinct party bracket on the card the engine would price for a week.

    The quote-builder fan-out (GAP-044) enumerates these *independent of the
    searched party* so every occupancy band renders as its own default-checked
    line. It carries only the bracket bounds — pricing each band is a separate
    `quote(party=…)` call, which is the single source of price truth.
    """

    min_party: int
    max_party: int


def _periods_cover_all_nights(periods: list[RatePeriod], week_nights: list[date]) -> bool:
    """True iff every night falls in at least one of `periods`.

    Gates on the **period** date-axis (`date_from <= night <= date_to`,
    inclusive) — the exact predicate `pick_band_for_night` uses — so the band
    enumerator agrees with the real quote about which nights a bracket covers,
    even if a band's own (transitional, pre-Unit-9) date columns ever drift from
    its period's. `week_nights` is the half-open `[from, to)` night list.
    """
    return all(
        any(period.date_from <= night <= period.date_to for period in periods)
        for night in week_nights
    )


class PricingEngine:
    """Stateless engine that turns (property, dates, party) into a Quote.

    `currency` is optional (GAP-014): when omitted, the engine prices in the
    covering rate plan's own currency — legacy behaviour — and the quote
    reports which one it used.
    """

    @classmethod
    def quote(
        cls,
        *,
        property: Any,
        date_from: date,
        date_to: date,
        party: int,
        currency: Currency | None = None,
        discount_code: str | None = None,
        opt_in_extras: list[int] | None = None,
        as_of: date | None = None,
        allow_projection: bool = True,
        context: PricingContext | None = None,
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
        # years". A caller-supplied `context` (from `load_context`) skips the
        # resolution entirely — the caller guarantees its plan covers the
        # quoted dates (e.g. a context loaded for a wider window).
        if context is None:
            context = cls._load_real_context(property, currency, date_from, date_to)
            if context is None and allow_projection:
                # `find_anchor_plan` is currency-keyed, so a currency-less quote
                # resolves one first via the canonical chain — the most recent
                # plan's currency, i.e. the villa's *current* currency after a
                # switch, never a stale pre-switch one (GAP-014).
                projection_currency = currency or resolve_property_currency(property)
                if projection_currency is not None:
                    context = RateProjectionService.project(
                        property=property,
                        date_from=date_from,
                        currency=projection_currency,
                    )
        if context is None:
            raise NoRateAvailable(
                f"No active RatePlan for property {getattr(property, 'pk', '?')} "
                f"currency {currency.code if currency else 'any'} "
                f"covering {date_from}..{date_to}"
            )
        plan = context.plan
        periods = context.periods
        bands_by_period = context.bands_by_period
        if currency is None:
            # Price in the rate card's own currency (legacy parity, GAP-014).
            currency = plan.currency

        # Changeover auto-shift (GAP-007): legacy nudged a non-conforming
        # arrival forward to the next valid changeover day rather than
        # rejecting it. The property's effective changeover day (a
        # ChangeOverRule window, else the settings chain) is the single source
        # of truth; `any` / unconstrained means no shift.
        changeover_day = ChangeoverService.effective_day(property, date_from)
        property_weekday = ChangeoverService.weekday_for(changeover_day)
        allowed_weekdays = {property_weekday} if property_weekday is not None else set()
        date_from, date_to, changeover_shifted_from = ChangeoverService.align_forward(
            allowed_weekdays, date_from, date_to
        )

        stay_nights = nights(date_from, date_to)

        villa_min_nights_default = cls._resolve_min_nights_default(property)

        lines: list[QuoteLine] = []
        chosen_periods: dict[int, RatePeriod] = {}
        winning_period: RatePeriod | None = None
        for night in stay_nights:
            # Distinguish "no band for this night at all" from "bands exist
            # for this night but none match the party size". The legacy
            # stored-proc defaulted to the highest bracket when party fell
            # outside every band; the rebuild raises `PartyOutOfRange`
            # instead (see `09-departures.md` bug #2). The tagged result
            # carries the disambiguation out of `pick_band_for_night`'s
            # single pass, so the engine doesn't have to re-walk the grid.
            pick = pick_band_for_night(periods, bands_by_period, night, party)
            if isinstance(pick, OutOfRange):
                raise PartyOutOfRange(
                    f"party={party} matches no RateBand bracket on plan {plan.pk} for {night}"
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
                            band_id=None,
                            period_id=None,
                            nightly=Decimal(plan.fallback_nightly),
                        )
                    )
                    continue
                raise NoRateAvailable(
                    f"No approved RateBand on plan {plan.pk} for {night} party={party}"
                )
            assert isinstance(pick, Picked)  # narrowing for mypy
            period, rule = pick.period, pick.rule
            if rule.is_poa:
                raise NoRateAvailable(
                    f"RateBand {rule.pk} is POA — cannot generate automatic quote"
                )
            nightly = rule_nightly(rule)
            lines.append(
                QuoteLine(
                    date=night,
                    band_id=rule.pk,
                    period_id=rule.period_id,
                    nightly=nightly,
                )
            )
            chosen_periods[period.pk] = period
            if winning_period is None:  # first real (non-fallback) night
                winning_period = period

        # The winning period is the one priced for the first real (non-fallback)
        # night. An all-fallback stay has no period to validate — mirror legacy,
        # which had no card concept on the fallback path, and skip the check.
        # The min/max-nights guard is strictest-wins across *every* period the
        # chosen stay touches (GAP-056 decision 4): the loud guard.
        stay_min_nights: int | None = None
        stay_max_nights: int | None = None
        if winning_period is not None:
            touched_periods = list(chosen_periods.values())
            cls._validate_periods_against_stay(
                touched_periods,
                nights=len(stay_nights),
                villa_min_nights_default=villa_min_nights_default,
            )
            stay_min_nights, stay_max_nights = cls._strict_stay_bounds(
                touched_periods, villa_min_nights_default
            )

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
            subtotal=rate_subtotal + extras_total,
            party=party,
            date_from=date_from,
            date_to=date_to,
            nights=len(stay_nights),
            as_of=as_of,
            discount_code=discount_code,
        )

        # Commission/tax are derived `price_basis`-aware (BUG-009, `04-pricing.md`
        # Services steps 8-10): a GROSS rate already includes them (carve out,
        # total == base), a NET rate is the owner net (gross up, total = base +
        # commission + tax). `plan.price_basis` is the sole pricing authority.
        base = rate_subtotal + extras_total - discount_total
        commission, tax = cls._derive_commission_and_tax(
            basis=plan.price_basis,
            base=base,
            commission_policy=cls._resolve_commission_policy(property, as_of),
            tax_rate=cls._resolve_tax_policy(property, as_of),
        )
        if plan.price_basis == PriceBasis.NET:
            total = (base + commission + tax).quantize(Decimal("0.01"))
        else:
            total = base.quantize(Decimal("0.01"))
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
            # The basis the money above was assembled under (BUG-009) — plans
            # are mutable, so a persisted snapshot must say which mode priced it.
            "price_basis": plan.price_basis,
            "winning_period_id": winning_period.pk if winning_period is not None else None,
            "changeover_shifted_from": (
                changeover_shifted_from.isoformat() if changeover_shifted_from is not None else None
            ),
            # A projected quote is a guide rate carried from a prior year; the
            # provenance lets the quotation generator / email render the "rates
            # carried over — inquire for accurate rate" marker and is persisted
            # into the booking snapshot.
            "is_projected": context.is_projected,
            "projection": context.projection,
            # Plan/card metadata the quote builder renders on each result line.
            # All in memory already — adding them costs no extra queries.
            # `inclusion` is derived from the property's date-banded
            # PropertyService rows (GAP-037) and still seeds staged-line
            # inclusions at creation (legacy ResService.cs:1241 seeded them from
            # the season).
            "inclusion": cls._derive_inclusions(property, date_from, date_to, context),
            "changeover_day": changeover_day if property_weekday is not None else None,
            # Report the STRICTEST bounds across every period the stay touches —
            # the same figures `_validate_periods_against_stay` enforces (GAP-056).
            # Reporting only the winning period's bounds would understate the
            # guard for a stay straddling periods with different min/max-nights.
            "min_nights": stay_min_nights,
            "max_nights": stay_max_nights,
            # >1 distinct party band on the winning period means the price moves
            # with the party size — surfaced as a badge on the result line.
            "occupancy_pricing": (
                winning_period is not None
                and len(
                    {(r.min_party, r.max_party) for r in bands_by_period.get(winning_period.pk, [])}
                )
                > 1
            ),
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

    @classmethod
    def load_context(
        cls,
        property: Any,
        *,
        date_from: date,
        date_to: date,
        currency: Currency | None = None,
    ) -> PricingContext | None:
        """Real-plan context covering ``[date_from, date_to)``, or ``None``
        when no active plan covers the range (the projection path) or the
        covering plan is misconfigured with no active periods.

        Lets a caller load the context once and reuse it — feed it to
        `stay_length_bounds` and back into `quote(context=...)` for any stay
        the plan covers, instead of paying the plan/card/rule queries twice.
        """
        try:
            return cls._load_real_context(property, currency, date_from, date_to)
        except NoRateAvailable:
            return None

    @classmethod
    def covering_bands(
        cls,
        *,
        property: Any,
        date_from: date,
        date_to: date,
        currency: Currency | None = None,
        context: PricingContext | None = None,
    ) -> list[OccupancyBand]:
        """Distinct party brackets the engine would price for the week
        ``[date_from, date_to)``, enumerated **independent of party**.

        This drives the quote-builder occupancy fan-out (GAP-044): the builder
        renders one default-checked line per band, so it needs every covering
        bracket, not just the one matching the searched party. Read-only; the
        `quote()` contract is untouched.

        Loads its own `PricingContext` when none is supplied — a
        flexible-changeover villa reaches the search layer with `context=None`
        yet may still be occupancy-priced, so a bare `context.bands_by_period`
        read would crash (fixes B1). Returns bands sorted by `min_party`; empty
        when no real plan covers the week (projection is out of scope — a
        guide-rate year has no banded default) or only a single bracket covers
        the week (the caller owns the ≥2 fan-out threshold).

        Bands (party-price rules) hang off periods, the disjoint date axis
        (GAP-056). A bracket covers the week iff *its own* bands — pooled across
        whatever periods the week spans — cover every night; a bracket that
        lapses mid-week is dropped rather than shown as bookable. The night-set
        is taken **after** the same changeover forward-shift `quote()` applies,
        so the bands here match the nights each band's own `quote()` would price.
        """
        if date_to <= date_from:
            return []
        if context is None:
            context = cls.load_context(
                property, date_from=date_from, date_to=date_to, currency=currency
            )
        if context is None:
            return []

        # Mirror quote()'s changeover auto-shift (GAP-007) so the enumerated
        # night-set matches what a per-band quote() would actually price; a
        # non-conforming arrival nudges forward to the next valid changeover
        # day. `align_forward` is idempotent on already-conforming dates, so
        # this is safe even when the caller passes pre-aligned block dates.
        changeover_day = ChangeoverService.effective_day(property, date_from)
        property_weekday = ChangeoverService.weekday_for(changeover_day)
        allowed_weekdays = {property_weekday} if property_weekday is not None else set()
        date_from, date_to, _shifted_from = ChangeoverService.align_forward(
            allowed_weekdays, date_from, date_to
        )

        week_nights = nights(date_from, date_to)
        if not week_nights:
            return []

        # Every band across every period of the plan; the disjoint period axis
        # means each night resolves to one period, so pooling bands by bracket
        # and checking night-coverage is the party-independent counterpart of
        # `pick_band_for_night`. A bracket covers the week iff the *periods* that
        # carry it — gated on the period date-axis, exactly like the real quote —
        # span every night; a bracket that lapses mid-week is dropped.
        all_rules = [rule for rules in context.bands_by_period.values() for rule in rules]
        brackets = {(rule.min_party, rule.max_party) for rule in all_rules}
        covering = [
            OccupancyBand(min_party=lo, max_party=hi)
            for (lo, hi) in brackets
            if _periods_cover_all_nights(
                [
                    period
                    for period in context.periods
                    if any(
                        (r.min_party, r.max_party) == (lo, hi)
                        for r in context.bands_by_period.get(period.pk, [])
                    )
                ],
                week_nights,
            )
        ]
        return sorted(covering, key=lambda band: (band.min_party, band.max_party))

    @classmethod
    def stay_length_bounds(cls, context: PricingContext) -> tuple[int, int | None]:
        """Aggregate (min_nights, max_nights) across the context's active
        periods, without running a quote.

        **Loosest-wins** (GAP-056 decision 4): a stay is valid when ANY period
        accepts it, so the bounds are the loosest across periods — a single
        uncapped period means no cap, and the min is the smallest period min.
        This is deliberately permissive: it is the stay-agnostic search
        pre-filter (`stay_options`), NOT the loud guard. Blanket strictest-wins
        here would clip the valid short off-peak stays that seasonal min-stay
        exists to enable. The eventual winning period may be stricter, in which
        case `quote()` itself raises (`_validate_periods_against_stay`).

        A period with `min_nights=None` inherits the villa default
        (`_resolve_min_nights_default`); there is no villa-level max (period
        `max_nights=None` simply means "no cap").
        """
        villa_default = cls._resolve_min_nights_default(context.property)
        if not context.periods:
            # A fallback-only plan (no periods) has no period bounds — the villa
            # default floors the min, with no cap.
            return (villa_default, None)
        min_nights = min(
            cls._effective_min_nights(period, villa_default) for period in context.periods
        )
        maxes = [period.max_nights for period in context.periods]
        if any(m is None for m in maxes):
            max_nights: int | None = None
        else:
            max_nights = max(m for m in maxes if m is not None)
        return (min_nights, max_nights)

    @staticmethod
    def _load_real_context(
        property: Any,
        currency: Currency | None,
        date_from: date,
        date_to: date,
    ) -> PricingContext | None:
        """Load the (plan, periods, rules) triple from a real plan covering the stay.

        With `currency=None`, plans in **any** currency are eligible and the
        canonical `pick_preferred_plan` tie-break chooses among them (GAP-014).

        Returns `None` when no active plan covers the whole `[date_from, date_to)`
        range — the signal for the caller to try a projection. A plan that *does*
        cover the dates but has no active periods is a misconfiguration, not a
        projection trigger, so it still raises `NoRateAvailable`.
        """
        covering = (
            RatePlan.objects.filter(
                property=property,
                is_active=True,
                effective_from__lte=date_from,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=date_to))
            .order_by("-effective_from", "-pk")
        )
        if currency is not None:
            plan = covering.filter(currency=currency).first()
        else:
            plan = pick_preferred_plan(list(covering.select_related("currency")), property)
        if plan is None:
            return None
        periods = list(
            RatePeriod.objects.filter(plan=plan, is_active=True).order_by("date_from", "pk")
        )
        # A plan with no periods is a misconfiguration UNLESS it opts into
        # fallback pricing (`fallback_nightly`), in which case an empty-period
        # context is valid and every night prices at the fallback rate. This is
        # the period-model successor to the legacy "empty card" all-fallback path
        # (a card with no rules used to yield a context; periods only exist where
        # rules do). No fallback + no periods → raise so the caller can project.
        if not periods and plan.fallback_nightly is None:
            raise NoRateAvailable(
                f"No active RatePeriod on plan {plan.pk} for {date_from}..{date_to}"
            )
        # Period activeness (filtered above) is now the sole gate — the old
        # RateCard is gone, so `RatePeriod.is_active` fully governs whether a
        # band prices.
        bands_by_period: dict[int, list[RateBand]] = {}
        approved_rules = RateBand.objects.filter(period__in=periods, is_approved=True)
        for rule in approved_rules:
            assert rule.period_id is not None  # filtered on period__in — never null
            bands_by_period.setdefault(rule.period_id, []).append(rule)
        return PricingContext(
            plan=plan, property=property, periods=periods, bands_by_period=bands_by_period
        )

    @staticmethod
    def _effective_min_nights(period: RatePeriod, villa_default: int) -> int:
        """A period's effective min-nights: its own override, else the villa
        default (GAP-056 decision 4 — `RatePeriod.min_nights` is a nullable
        override on top of `PropertySettings.min_nights_rental`)."""
        return period.min_nights if period.min_nights is not None else villa_default

    @staticmethod
    def _resolve_min_nights_default(property: Any) -> int:
        """Villa-level default min-nights, resolved **defensively**.

        Reuses `PropertySettings.min_nights_rental` (GAP-056 decision 4 — no new
        Property field). The hand-built pricing/reservations test properties have
        no `PropertySettings` / `GroupSettings` row, so both the reverse accessor
        and `effective()`'s group dereference can raise; every failure falls back
        to the legacy default of 1.
        """
        settings = getattr(property, "settings", None)
        if settings is None:
            return 1
        try:
            value = settings.effective("min_nights_rental")
        except (AttributeError, ObjectDoesNotExist):
            value = settings.min_nights_rental
        return value if value is not None else 1

    @classmethod
    def _strict_stay_bounds(
        cls, periods: list[RatePeriod], villa_min_nights_default: int
    ) -> tuple[int, int | None]:
        """**Strictest-wins** (min, max) across the periods a stay touches.

        min = the largest effective min; max = the smallest non-null max (None
        when no period caps). Shared by the loud guard and the breakdown so the
        reported bounds match what is actually enforced (GAP-056 decision 4).
        """
        strict_min = max(
            cls._effective_min_nights(period, villa_min_nights_default) for period in periods
        )
        capped = [period.max_nights for period in periods if period.max_nights is not None]
        strict_max = min(capped) if capped else None
        return strict_min, strict_max

    @classmethod
    def _validate_periods_against_stay(
        cls,
        periods: list[RatePeriod],
        *,
        nights: int,
        villa_min_nights_default: int,
    ) -> None:
        """The loud min/max-nights guard: **strictest-wins** across every period
        the chosen stay touches (GAP-056 decision 4). A stay that violates either
        bound raises `MinNightsNotMet`.
        """
        strict_min, strict_max = cls._strict_stay_bounds(periods, villa_min_nights_default)
        if nights < strict_min:
            raise MinNightsNotMet(f"stay requires min_nights={strict_min}, got {nights}")
        if strict_max is not None and nights > strict_max:
            raise MinNightsNotMet(f"stay caps max_nights={strict_max}, got {nights}")

    @staticmethod
    def _apply_discounts(
        *,
        property: Any,
        subtotal: Decimal,
        party: int,
        date_from: date,
        date_to: date,
        nights: int,
        as_of: date,
        discount_code: str | None,
    ) -> Decimal:
        # GAP-056 Unit 7: discounts are property-scoped (the card scope is gone).
        qs = (
            Discount.objects.filter(
                property=property,
                is_active=True,
                valid_from__lte=date_from,
                valid_to__gte=date_from,
            )
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
        `_resolve_commission_policy`/`_resolve_tax_policy` once
        `PropertyFinance.effective_*` accepts `as_of` and returns the
        scalar/attribute shape directly.
        """
        try:
            return resolver(as_of=as_of)
        except TypeError:
            return resolver()

    @classmethod
    def _derive_inclusions(
        cls,
        property: Any,
        date_from: date,
        date_to: date,
        context: PricingContext,
    ) -> str:
        """The guest-facing "what's included" blob for this stay (GAP-037).

        Joins the `copy` of the property's active services whose absolute date
        band overlaps the (changeover-shifted) stay. For a projected quote the
        bands live in the anchor's source year, so the stay is mapped back by the
        whole-year delta first — a future-year July quote still finds the summer
        chef it was carried from.
        """
        q_from, q_to = date_from, date_to
        if context.is_projected and context.projection is not None:
            year_delta = context.projection["target_year"] - context.projection["source_year"]
            q_from = keep_calendar_date(date_from, -year_delta)
            q_to = keep_calendar_date(date_to, -year_delta)
        services = PropertyService.objects.filter(property=property, is_active=True).order_by(
            "sort_order", "id"
        )
        return "\n".join(
            svc.copy
            for svc in services
            if date_ranges_overlap(q_from, q_to, svc.applies_from, svc.applies_to)
        )

    @staticmethod
    def _resolve_commission_policy(property: Any, as_of: date) -> tuple[str, Decimal] | None:
        """The property's effective `(calculation_type, amount)` commission,
        or None when no commission is configured.

        Tolerates both the live no-arg dict resolver and the future
        `as_of=`/scalar shape (see `_call_finance_resolver`); a bare scalar
        is read as a percentage.
        """
        finance = getattr(property, "finance", None)
        if finance is None:
            return None
        resolver = getattr(finance, "effective_commission", None)
        if resolver is None:
            return None
        commission = PricingEngine._call_finance_resolver(resolver, as_of)
        if commission is None:
            return None
        if isinstance(commission, dict):
            calc_type = commission.get("calculation_type")
            amount = commission.get("amount")
        else:
            calc_type = CommissionCalcType.PERCENT
            amount = commission
        if amount is None or calc_type not in CommissionCalcType.values:
            return None
        return (calc_type, Decimal(str(amount)))

    @staticmethod
    def _resolve_tax_policy(property: Any, as_of: date) -> Decimal | None:
        """The property's effective tax rate (percentage), or None when tax
        is unconfigured or the property is exempt — exemption skips the tax
        maths entirely in both modes (spec step 9).
        """
        finance = getattr(property, "finance", None)
        if finance is None:
            return None
        resolver = getattr(finance, "effective_tax_policy", None)
        if resolver is None:
            return None
        policy = PricingEngine._call_finance_resolver(resolver, as_of)
        if policy is None:
            return None
        if isinstance(policy, dict):
            if policy.get("is_exempt"):
                return None
            rate = policy.get("percentage")
        else:
            if getattr(policy, "is_exempt", False):
                return None
            rate = getattr(policy, "rate", None)
        if rate is None:
            return None
        return Decimal(str(rate))

    @staticmethod
    def _derive_commission_and_tax(
        *,
        basis: str,
        base: Decimal,
        commission_policy: tuple[str, Decimal] | None,
        tax_rate: Decimal | None,
    ) -> tuple[Decimal, Decimal]:
        """Mode-aware commission + tax per `04-pricing.md` Services steps 8-9.

        GROSS (the rate includes both — carve out): `tax = base x rate/100`,
        `commission = (base - tax) x pct/100`. NET (the rate is the owner
        net — gross up): `commission = base/(1 - pct/100) - base`,
        `tax = (base + commission)/(1 - rate/100) - (base + commission)`.
        A fixed commission is the flat amount in both modes and enters the
        NET tax base (legacy `RatesModel.Calculate()` parity).

        Quantization order is pinned to match the GAP-035 entry-form hint
        (`frontend/src/lib/pricing/netGross.ts`): the RAW (unquantized)
        commission feeds the tax base — and the raw tax the GROSS commission
        base — with each component quantized to 0.01 only at the end.

        Guards — a deliberate divergence from legacy (which leaves fields
        unset on pct=100 via a swallowed exception and goes negative above):
        `base <= 0` -> both 0.00; a tax rate >= 100 -> tax 0.00 in both modes
        (NET: divide-by-<=0 on the gross-up; GROSS: a tax >= the gross would
        flip the commission base negative); a NET commission pct >= 100
        (divide-by-<=0) -> commission 0.00. A GROSS percent commission is
        unguarded — with a sane tax it is always >= 0, and an oversized pct
        is a real owner deficit, like an oversized fixed commission.
        """
        zero = Decimal("0.00")
        if base <= 0:
            return zero, zero
        hundred = Decimal(100)
        calc_type, amount = commission_policy if commission_policy is not None else (None, None)
        rate = tax_rate if tax_rate is not None and tax_rate < hundred else None

        raw_commission = Decimal(0)
        raw_tax = Decimal(0)
        if basis == PriceBasis.NET:
            if calc_type == CommissionCalcType.FIXED and amount is not None:
                raw_commission = amount
            elif calc_type == CommissionCalcType.PERCENT and amount is not None:
                if amount < hundred:
                    raw_commission = base / (1 - amount / hundred) - base
            if rate is not None:
                tax_base = base + raw_commission
                raw_tax = tax_base / (1 - rate / hundred) - tax_base
        else:
            if rate is not None:
                raw_tax = base * rate / hundred
            if calc_type == CommissionCalcType.FIXED and amount is not None:
                raw_commission = amount
            elif calc_type == CommissionCalcType.PERCENT and amount is not None:
                raw_commission = (base - raw_tax) * amount / hundred
        return raw_commission.quantize(Decimal("0.01")), raw_tax.quantize(Decimal("0.01"))
