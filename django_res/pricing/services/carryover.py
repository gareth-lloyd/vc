"""On-demand promotion of a projected year into editable rate rows.

The demoted carryover verb. Lazy projection (`pricing.services.projection`) serves
every next-year *quote* without writing anything; this service exists for the
moment staff want **editable** rows for a year — an owner has returned real
numbers, or they want to hand-tune the guide before confirming. It clones the
anchor year forward into real `RatePlan` / `RatePeriod` / `RateBand` rows,
reusing the same date-map + uplift the projection uses, so the materialised rows
match the guide a quote would have shown.

This is deliberately **not** a Celery beat task: nothing rolls the whole portfolio
forward speculatively. It is invoked per-property, on demand, from the admin action
or the carry-forward endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import structlog
from django.db import transaction

from core.exceptions import NoRateAvailable
from pricing.models import RateBand, RatePeriod, RatePlan
from pricing.services.flattening import flatten_rate_grid
from pricing.services.period_names import uniform_or_derived_name
from pricing.services.projection import (
    DateMap,
    RateProjectionService,
    apply_uplift,
    keep_calendar_date,
    load_anchor_periods_with_rules,
    map_anchor_sources,
    shift_to_changeover_weekday,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class _CarriedRate:
    """The flattener payload: prices + metadata a materialised row carries.

    `min_nights`/`max_nights` and `period_name` ride along from the band's
    source period so the materialised period can carry them (GAP-059: the
    curated label survives the yearly carry).
    """

    source_pk: int
    nightly: Decimal | None
    weekly: Decimal | None
    is_poa: bool
    notes: str
    min_nights: int | None
    max_nights: int | None
    period_name: str


class RateCarryoverService:
    """Write editable rate rows for a target year from the most recent prior year."""

    @classmethod
    def materialise(
        cls,
        property: Any,
        *,
        target_year: int,
        currency: Any,
        date_map: DateMap = shift_to_changeover_weekday,
        uplift: Decimal = Decimal("0"),
    ) -> RatePlan:
        """Clone the anchor year forward into real rows for `target_year`.

        Idempotent per (property, currency, target_year): if a plan already starts
        in that year it is returned untouched, so a double-click or re-run never
        duplicates. Raises `NoRateAvailable` when there is no prior year to carry
        from. Rule dates move via `date_map` (span-preserving); the plan envelope
        moves by calendar year so its `effective_from` lands cleanly in the target
        year. Prices scale by `1 + uplift` (default verbatim).
        """
        existing = (
            RatePlan.objects.filter(
                property=property,
                currency=currency,
                effective_from__year=target_year,
            )
            .order_by("pk")
            .first()
        )
        if existing is not None:
            return existing

        anchor = RateProjectionService.find_anchor_plan(property, currency, date(target_year, 1, 1))
        if anchor is None:
            raise NoRateAvailable(
                f"No prior RatePlan to carry forward for property "
                f"{getattr(property, 'pk', '?')} currency {currency.code} into {target_year}"
            )

        year_delta = target_year - anchor.effective_from.year
        factor = Decimal("1") + uplift

        # Project the anchor into flattener inputs via the shared builder —
        # the same geometry and precedence the projection uses, so the
        # materialised rows price every night exactly as the projection would.
        # Only active periods / approved bands — the exact set a real quote
        # prices — via the shared batched loader; prices are uplifted here.
        sources = map_anchor_sources(
            load_anchor_periods_with_rules(anchor),
            year_delta,
            date_map,
            lambda period, rule: _CarriedRate(
                source_pk=rule.pk,
                nightly=apply_uplift(rule.nightly, factor),
                weekly=apply_uplift(rule.weekly, factor),
                is_poa=rule.is_poa,
                notes=rule.notes,
                min_nights=period.min_nights,
                max_nights=period.max_nights,
                period_name=period.name,
            ),
        )

        # Date-mapping can land adjacent source periods on top of each other
        # (a leap-year range spanning Feb 29 keeps its span while the calendar
        # loses a day; the weekday map can shift neighbours in opposite
        # directions by up to 3 days each), and the periods-disjoint EXCLUDE
        # would turn that into an `IntegrityError`. The shared flattener
        # (BUG-016) resolves collisions into the (date x party)-disjoint grid;
        # a band only vanishes when every one of its cells was claimed.
        flattened = flatten_rate_grid(sources)
        for dropped in flattened.dropped_sources:
            logger.info(
                "pricing.carryover.rule_skipped",
                source_rule_id=dropped.payload.source_pk,
                reason="date_map_collision_emptied_range",
            )
        for clipped in flattened.party_clipped:
            # The band survives but with a mutated party bracket — leave an
            # audit trail so a carried year's shape drift is explicable.
            logger.info(
                "pricing.carryover.rule_party_clipped",
                source_rule_id=clipped.payload.source_pk,
                reason="date_map_collision_clipped_party_bracket",
            )

        with transaction.atomic():
            new_plan = RatePlan.objects.create(
                property=property,
                currency=currency,
                name=f"{anchor.name} ({target_year})",
                price_basis=anchor.price_basis,
                fallback_nightly=anchor.fallback_nightly,
                effective_from=keep_calendar_date(anchor.effective_from, year_delta),
                effective_to=(
                    keep_calendar_date(anchor.effective_to, year_delta)
                    if anchor.effective_to is not None
                    else None
                ),
                is_active=anchor.is_active,
                # GAP-037: inclusions are property-scoped PropertyService rows
                # that already persist across years — nothing to carry per-plan.
                notes=f"Carried forward from plan #{anchor.pk} ({anchor.effective_from.year}).",
            )
            # One RatePeriod per flat period. `bands` is winner-first
            # (precedence order), so bands[0] (lowest source pk) carries the
            # winning min/max nights.
            for flat_period in flattened.periods:
                # GAP-059 name rule lives in `uniform_or_derived_name`.
                winner = flat_period.bands[0].source.payload
                new_period = RatePeriod.objects.create(
                    plan=new_plan,
                    name=uniform_or_derived_name(
                        (band.source.payload.period_name for band in flat_period.bands),
                        flat_period.date_from,
                        flat_period.date_to,
                    ),
                    date_from=flat_period.date_from,
                    date_to=flat_period.date_to,
                    min_nights=winner.min_nights,
                    max_nights=winner.max_nights,
                )
                for band in flat_period.bands:
                    carried = band.source.payload
                    RateBand.objects.create(
                        period=new_period,
                        min_party=band.min_party,
                        max_party=band.max_party,
                        nightly=carried.nightly,
                        weekly=carried.weekly,
                        is_poa=carried.is_poa,
                        is_approved=True,
                        is_locked=False,
                        notes=carried.notes,
                    )
        return new_plan
