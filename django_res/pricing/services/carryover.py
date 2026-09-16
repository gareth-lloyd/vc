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
from django.utils import timezone

from core.exceptions import NoRateAvailable, RegimeConflict
from pricing.models import RateBand, RatePeriod, RatePlan
from pricing.services.flattening import flatten_rate_grid
from pricing.services.intervals import Interval, subtract_intervals
from pricing.services.period_names import uniform_or_derived_name
from pricing.services.projection import (
    DateMap,
    RateProjectionService,
    apply_uplift,
    load_anchor_periods_with_rules,
    map_anchor_sources,
    shift_to_changeover_weekday,
)
from pricing.services.regime import period_overlap_guard
from pricing.signals import suppress_summary_rebuild

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

        GAP-110: the rows land on the anchor's own regime plan (a date-less
        bucket holding every year's periods) — no plan is ever created here.
        Idempotent per (property, currency, target_year): if any active period
        of an active plan in the regime already starts in that year, that plan
        is returned untouched, so a double-click or re-run never duplicates.
        A target year owned only by *withdrawn* rows (an inactive period, or a
        retired plan's) is refused as `RegimeConflict`: those rows still own
        their dates, so the carry would silently land nothing — the operator
        reactivates or deletes them first. Raises `NoRateAvailable` when there
        is no prior year to carry from. Rule dates move via `date_map`
        (span-preserving) and are clipped around a straddling neighbour year's
        rows. Prices scale by `1 + uplift` (default verbatim).
        """
        in_target_year = (
            RatePeriod.objects.filter(
                property=property, currency=currency, date_from__year=target_year
            )
            .select_related("plan__currency")
            .order_by("-is_active", "-plan__is_active", "date_from", "pk")
        )
        owner = in_target_year.first()
        if owner is not None:
            if owner.is_active and owner.plan.is_active:
                return owner.plan
            raise RegimeConflict(
                f"{target_year} already has withdrawn rate periods for "
                f"{getattr(property, 'name', property)} in {currency.code} "
                f'(e.g. "{owner.name}" on plan "{owner.plan.name}"); reactivate or delete '
                "them before carrying forward."
            )

        anchor = RateProjectionService.find_anchor(property, currency, target_year)
        if anchor is None:
            raise NoRateAvailable(
                f"No prior rate periods to carry forward for property "
                f"{getattr(property, 'pk', '?')} currency {currency.code} into {target_year}"
            )

        year_delta = target_year - anchor.source_year
        factor = Decimal("1") + uplift

        # Project the anchor into flattener inputs via the shared builder —
        # the same geometry and precedence the projection uses, so the
        # materialised rows price every night exactly as the projection would.
        # Only active periods / approved bands — the exact set a real quote
        # prices — via the shared batched loader; prices are uplifted here.
        sources = map_anchor_sources(
            load_anchor_periods_with_rules(anchor.plan, anchor.source_year),
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

        # The no-overlap EXCLUDE is regime-wide and ungated by `is_active`, so
        # a mapped period can still land on dates a *neighbouring* year owns —
        # last year's tail straddling New Year under this year's January
        # period, or next year's rows (already carried) under this year's
        # December tail. Clip the mapped periods around every existing
        # (property, currency) period in the mapped window; a remainder keeps
        # its bands and min/max nights. GAP-037: inclusions are property-scoped
        # PropertyService rows that already persist across years — nothing to
        # carry per plan.
        owned: list[Interval] = []
        if flattened.periods:
            owned = [
                (date_from.toordinal(), date_to.toordinal())
                for date_from, date_to in RatePeriod.objects.filter(
                    property=property,
                    currency=currency,
                    date_to__gte=min(p.date_from for p in flattened.periods),
                    date_from__lte=max(p.date_to for p in flattened.periods),
                ).values_list("date_from", "date_to")
            ]
        written = 0
        # The guard still maps a raced constraint violation (a period written
        # between the clip and the insert) to a 409 rather than a 500.
        with period_overlap_guard():
            # One RatePeriod per surviving flat-period remainder. `bands` is
            # winner-first (precedence order), so bands[0] (lowest source pk)
            # carries the winning min/max nights.
            for flat_period in flattened.periods:
                span: Interval = (
                    flat_period.date_from.toordinal(),
                    flat_period.date_to.toordinal(),
                )
                remainders = subtract_intervals([span], owned)
                if remainders != [span]:
                    logger.info(
                        "pricing.carryover.period_clipped",
                        property_id=getattr(property, "pk", None),
                        currency=currency.code,
                        date_from=flat_period.date_from.isoformat(),
                        date_to=flat_period.date_to.isoformat(),
                        remainders=len(remainders),
                        reason=(
                            "regime_already_owns_dates"
                            if remainders
                            else "regime_already_owns_every_date"
                        ),
                    )
                winner = flat_period.bands[0].source.payload
                for low, high in remainders:
                    assert high is not None  # date intervals are always bounded
                    date_from, date_to = date.fromordinal(low), date.fromordinal(high)
                    new_period = RatePeriod.objects.create(
                        plan=anchor.plan,
                        # GAP-059 name rule lives in `uniform_or_derived_name`;
                        # a derived placeholder names the remainder's own span.
                        name=uniform_or_derived_name(
                            (band.source.payload.period_name for band in flat_period.bands),
                            date_from,
                            date_to,
                        ),
                        date_from=date_from,
                        date_to=date_to,
                        min_nights=winner.min_nights,
                        max_nights=winner.max_nights,
                    )
                    written += 1
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
                            # GAP-114: a carry is a copy nobody has signed off —
                            # indicative until staff confirm it (`confirm` below
                            # or the band PATCH). Legacy `CarriedRates`, same idea.
                            is_indicative=True,
                            notes=carried.notes,
                        )
        # The provenance record: rows carry no source pointer (RatePeriod has
        # no notes column; band notes are the source band's own), so the
        # what/where-from/uplift of a carry lives in the log stream alongside
        # the AuditLog rows the `.create()` calls emit.
        logger.info(
            "pricing.carryover.materialised",
            property_id=getattr(property, "pk", None),
            currency=currency.code,
            plan_id=anchor.plan.pk,
            source_year=anchor.source_year,
            target_year=target_year,
            uplift=str(uplift),
            date_map=date_map.__name__,
            periods_written=written,
        )
        return anchor.plan

    @staticmethod
    def confirm(
        plan: RatePlan, *, date_from: date | None = None, date_to: date | None = None
    ) -> int:
        """GAP-114: mark the plan's indicative bands as owner-confirmed.

        Confirms whole periods: every indicative band on a period that
        overlaps the inclusive ``date_from..date_to`` window (both bounds or
        neither — one alone is a ``ValueError``, never "the whole plan"),
        skipping periods that have already elapsed (decision 10 — historical
        rates are frozen as they were; same test as ``RatePeriod.is_historical``).
        Returns the number of bands cleared. Each band goes through ``save()``
        so the audit trail records who confirmed what and when; the summary
        rebuild is suppressed because the cache never reads the flag.
        """
        if (date_from is None) != (date_to is None):
            raise ValueError("confirm needs both date_from and date_to, or neither")
        bands = RateBand.objects.filter(
            period__plan=plan, is_indicative=True, period__date_to__gte=timezone.localdate()
        )
        if date_from is not None and date_to is not None:
            bands = bands.filter(period__date_from__lte=date_to, period__date_to__gte=date_from)
        with transaction.atomic(), suppress_summary_rebuild():
            confirmed = 0
            for band in bands:
                band.is_indicative = False
                band.save(update_fields=["is_indicative", "updated_at"])
                confirmed += 1
        logger.info(
            "pricing.rates.confirmed",
            plan_id=plan.pk,
            date_from=date_from.isoformat() if date_from else None,
            date_to=date_to.isoformat() if date_to else None,
            bands_confirmed=confirmed,
        )
        return confirmed

    @staticmethod
    def next_target_year(property: Any, currency: Any) -> int | None:
        """The year after the regime's latest active period (of an active
        plan) — the year the admin action carries into. `None` when the
        regime has no live periods (nothing to carry)."""
        latest = (
            RatePeriod.objects.filter(
                property=property, currency=currency, is_active=True, plan__is_active=True
            )
            .order_by("-date_from")
            .values_list("date_from", flat=True)
            .first()
        )
        return None if latest is None else latest.year + 1
