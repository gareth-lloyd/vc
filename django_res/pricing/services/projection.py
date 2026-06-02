"""Lazy rate projection for future years.

At this time of year clients inquire for *next* year, but only ~10% of next-year
rates are confirmed. Rather than materialising a speculative clone of every
villa's rate graph, the engine *derives* a guide rate at quote time from the most
recent year that has rates, flags the quote `is_projected`, and writes nothing.

This module owns three things:

* the two swappable date-map functions (`shift_to_changeover_weekday`,
  `keep_calendar_date`) that move a source-year date into the target year;
* `RateProjectionService`, which finds the anchor plan and builds an in-memory
  `PricingContext` the engine can price exactly like a real one;
* `PricingContext`, the (plan, cards, rules_by_card) triple the engine consumes
  whether it came from the database (real) or from a projection (synthesized).

The synthesized plan / cards / rules are **unsaved** model instances whose `pk`
is set to the source row's pk. That gives the quote breakdown free traceability
(`QuoteLine.rule_id` / `winning_card_id` point at the real anchor rows) without
ever touching the database. See `04-pricing.md` "Projected pricing for future
years".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from pricing.models import Currency, RateCard, RatePlan, RateRule

# A date-map shifts a single source date by `year_delta` whole years into the
# target year. It is applied independently to each rule endpoint, so it must be a
# pure function of (date, year_delta) — no cross-endpoint state.
DateMap = Callable[[date, int], date]


def keep_calendar_date(d: date, year_delta: int) -> date:
    """Keep the same calendar date, just relabel the year (1 Jul -> 1 Jul).

    Feb 29 has no counterpart in a non-leap target year; it falls back to Feb 28.
    """
    try:
        return d.replace(year=d.year + year_delta)
    except ValueError:
        return d.replace(year=d.year + year_delta, day=28)


def shift_to_changeover_weekday(d: date, year_delta: int) -> date:
    """Preserve the weekday, nudging to the nearest same-weekday date.

    A Saturday-to-Saturday week stays Saturday-to-Saturday in the new year — the
    way villas with a `ChangeOverRule` actually let. The date moves by the minimal
    number of days (ties resolve backwards, the earlier date).

    This is the **default** date-map. Whether the business ultimately wants this or
    `keep_calendar_date` is an open follow-up pending Bryony's listing Loom
    (`10-decisions.md` "Carryover date-mapping rule"); the engine takes the
    function as a parameter so nothing is hard-coded.
    """
    naive = keep_calendar_date(d, year_delta)
    back = (naive.weekday() - d.weekday()) % 7  # days back to the source weekday
    if back == 0:
        return naive
    forward = 7 - back
    if back <= forward:
        return naive - timedelta(days=back)
    return naive + timedelta(days=forward)


def map_range(
    date_from: date, date_to: date, year_delta: int, date_map: DateMap
) -> tuple[date, date]:
    """Move a rule's date range into the target year, preserving its night count.

    Only the start is mapped through `date_map`; the end follows rigidly by the
    original span. Mapping each endpoint independently could invert a short range
    (and trip the `date_from < date_to` constraint when carryover saves it), and
    would silently change the night count — neither of which the operator intends
    when carrying a Saturday-to-Saturday week forward.
    """
    new_from = date_map(date_from, year_delta)
    return new_from, new_from + (date_to - date_from)


@dataclass
class PricingContext:
    """The (plan, cards, rules_by_card) triple the engine prices.

    `is_projected` is True when the triple was synthesized from an anchor year by
    `RateProjectionService.project`; `projection` then carries the snapshotable
    provenance (source plan / years / uplift / date-map) the quote surfaces.
    """

    plan: RatePlan
    cards: list[RateCard]
    rules_by_card: dict[int, list[RateRule]]
    is_projected: bool = False
    projection: dict[str, Any] | None = field(default=None)


def apply_uplift(value: Decimal | None, factor: Decimal) -> Decimal | None:
    """Scale a (possibly null) price by `factor`, rounded to 2dp. Null stays null."""
    if value is None:
        return None
    return (Decimal(value) * factor).quantize(Decimal("0.01"))


class RateProjectionService:
    """Derive a guide-rate `PricingContext` for a year that has no rate plan."""

    @staticmethod
    def find_anchor_plan(
        property: Any,
        currency: Currency,
        date_from: date,
        date_to: date,
    ) -> RatePlan | None:
        """The most recent active plan for this property+currency in an *earlier*
        year than the requested stay.

        `None` when the villa has no prior rates in this currency (a brand-new
        villa), which the caller turns into a normal `NoRateAvailable`. Restricting
        the anchor to `effective_from` before 1 Jan of the target year both
        guarantees a forward projection (`year_delta >= 1`) and stops a partial
        same-year plan — or a previously materialised carry-forward — from anchoring
        on itself.
        """
        target_year = date_from.year
        return (
            RatePlan.objects.filter(
                property=property,
                currency=currency,
                is_active=True,
                effective_from__lt=date(target_year, 1, 1),
            )
            .order_by("-effective_from", "-pk")
            .first()
        )

    @classmethod
    def project(
        cls,
        *,
        property: Any,
        date_from: date,
        date_to: date,
        currency: Currency,
        date_map: DateMap = shift_to_changeover_weekday,
        uplift: Decimal = Decimal("0"),
    ) -> PricingContext | None:
        """Synthesize an in-memory plan for `date_from`'s year from the anchor.

        Returns `None` when there is no anchor (or it has no active cards), so the
        caller can fall through to the usual `NoRateAvailable`. Rule dates move via
        `date_map`; the plan envelope always moves by calendar year (its precise
        weekday is irrelevant — only its rules are priced). Prices are multiplied by
        `1 + uplift`; the default `0` carries last year's figure verbatim.
        """
        anchor = cls.find_anchor_plan(property, currency, date_from, date_to)
        if anchor is None:
            return None

        cards = list(
            RateCard.objects.filter(plan=anchor, is_active=True).order_by("sort_order", "pk")
        )
        if not cards:
            return None

        target_year = date_from.year
        source_year = anchor.effective_from.year
        year_delta = target_year - source_year
        factor = Decimal("1") + uplift

        proj_plan = RatePlan(
            id=anchor.pk,
            property_id=anchor.property_id,
            currency_id=anchor.currency_id,
            name=anchor.name,
            price_basis=anchor.price_basis,
            fallback_nightly=anchor.fallback_nightly,
            effective_from=keep_calendar_date(anchor.effective_from, year_delta),
            effective_to=(
                keep_calendar_date(anchor.effective_to, year_delta)
                if anchor.effective_to is not None
                else None
            ),
            is_active=anchor.is_active,
            inclusion=anchor.inclusion,
        )

        proj_cards: list[RateCard] = []
        rules_by_card: dict[int, list[RateRule]] = {}
        for card in cards:
            proj_card = RateCard(
                id=card.pk,
                plan_id=anchor.pk,
                name=card.name,
                description=card.description,
                min_nights=card.min_nights,
                max_nights=card.max_nights,
                sort_order=card.sort_order,
                is_active=card.is_active,
            )
            proj_cards.append(proj_card)
            proj_rules: list[RateRule] = []
            # Mirror the engine's real-path filter: unapproved imports never
            # quote, so they never seed a projection either.
            for rule in RateRule.objects.filter(card=card, is_approved=True):
                new_from, new_to = map_range(rule.date_from, rule.date_to, year_delta, date_map)
                proj_rules.append(
                    RateRule(
                        id=rule.pk,
                        card_id=card.pk,
                        date_from=new_from,
                        date_to=new_to,
                        min_party=rule.min_party,
                        max_party=rule.max_party,
                        priority=rule.priority,
                        nightly=apply_uplift(rule.nightly, factor),
                        weekly=apply_uplift(rule.weekly, factor),
                        is_poa=rule.is_poa,
                        is_approved=True,
                    )
                )
            rules_by_card[card.pk] = proj_rules

        projection = {
            "source_plan_id": anchor.pk,
            "source_year": source_year,
            "target_year": target_year,
            "uplift_pct": str((uplift * Decimal("100")).quantize(Decimal("0.01"))),
            "date_map": date_map.__name__,
        }
        return PricingContext(
            plan=proj_plan,
            cards=proj_cards,
            rules_by_card=rules_by_card,
            is_projected=True,
            projection=projection,
        )
