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

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import structlog
from django.db import transaction

from core.exceptions import NoRateAvailable
from pricing.models import RateBand, RatePeriod, RatePlan
from pricing.services.extras import date_ranges_overlap
from pricing.services.period_names import derive_period_name
from pricing.services.projection import (
    DateMap,
    RateProjectionService,
    apply_uplift,
    keep_calendar_date,
    load_anchor_periods_with_rules,
    map_range,
    shift_to_changeover_weekday,
)
from pricing.services.segmentation import segment_card_rules

logger = structlog.get_logger(__name__)


@dataclass
class _Band:
    """A projected party band with its (date-mapped) span and carried metadata.

    Feeds both the collision resolver (`_unclaimed_segments`) and the date
    segmentation (`segment_card_rules`, which reads `date_from`/`date_to`/
    `min_party`/`max_party`). `min_nights`/`max_nights` and `period_name` ride
    along from the band's source period so the materialised period can carry
    them (GAP-059: the curated label survives the yearly carry).
    """

    source_pk: int
    date_from: date
    date_to: date
    min_party: int
    max_party: int
    nightly: Decimal | None
    weekly: Decimal | None
    is_poa: bool
    notes: str
    min_nights: int | None
    max_nights: int | None
    period_name: str


def _unclaimed_segments(band: _Band, claimed: list[_Band]) -> list[tuple[date, date]]:
    """Date sub-ranges of a mapped band not covered by any party-overlapping
    already-claimed segment, in date order.

    Date-mapping can land adjacent source periods on top of each other (a
    leap-year range spanning Feb 29 keeps its span while the calendar loses a
    day; the weekday map can shift neighbours in opposite directions by up to
    3 days each), and the periods-disjoint EXCLUDE would turn that into an
    `IntegrityError`. Bands claim space in ascending source-pk order — the same
    precedence `pick_band_for_night` gives colliding in-memory projected bands —
    so the materialised rows price every night exactly as the projection would.
    A remainder can sit on either side of a claim (or both, splitting the band
    into two rows).
    """
    segments = [(band.date_from, band.date_to)]
    for prev in claimed:
        if band.min_party > prev.max_party or band.max_party < prev.min_party:
            continue
        survivors: list[tuple[date, date]] = []
        for lo, hi in segments:
            if not date_ranges_overlap(lo, hi, prev.date_from, prev.date_to):
                survivors.append((lo, hi))
                continue
            if lo < prev.date_from:
                survivors.append((lo, prev.date_from - timedelta(days=1)))
            if prev.date_to < hi:
                survivors.append((prev.date_to + timedelta(days=1), hi))
        segments = survivors
    return sorted(segments)


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

        # Flatten the anchor into projected bands: each period's dates mapped
        # forward, each band's prices uplifted. `source_pk` preserves the
        # precedence `pick_band_for_night` gives colliding projected bands
        # (lowest pk wins), and each band carries its source period's min/max
        # nights so the materialised period can too (parity with `project`,
        # which copies them). Only active periods / approved bands — the exact
        # set a real quote prices — via the shared batched loader.
        projected: list[_Band] = []
        for period, rules in load_anchor_periods_with_rules(anchor):
            new_from, new_to = map_range(period.date_from, period.date_to, year_delta, date_map)
            for rule in rules:
                projected.append(
                    _Band(
                        source_pk=rule.pk,
                        date_from=new_from,
                        date_to=new_to,
                        min_party=rule.min_party,
                        max_party=rule.max_party,
                        nightly=apply_uplift(rule.nightly, factor),
                        weekly=apply_uplift(rule.weekly, factor),
                        is_poa=rule.is_poa,
                        notes=rule.notes,
                        min_nights=period.min_nights,
                        max_nights=period.max_nights,
                        period_name=period.name,
                    )
                )

        # Resolve date-mapping collisions in source-pk order into a
        # (date x party)-disjoint band set. Inclusive periods (GAP-056) admit
        # single-day segments (lo == hi); only inverted ranges (lo > hi, when a
        # claim abuts a boundary) are dropped.
        # `disjoint` doubles as the running claim set `_unclaimed_segments` reads
        # to trim later bands, and as the final input to `segment_card_rules`.
        disjoint: list[_Band] = []
        for band in sorted(projected, key=lambda b: b.source_pk):
            segments = [(lo, hi) for lo, hi in _unclaimed_segments(band, disjoint) if lo <= hi]
            if not segments:
                logger.info(
                    "pricing.carryover.rule_skipped",
                    source_rule_id=band.source_pk,
                    reason="date_map_collision_emptied_range",
                )
                continue
            for lo, hi in segments:
                disjoint.append(replace(band, date_from=lo, date_to=hi))

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
            # Group the disjoint bands onto a shared disjoint RatePeriod date axis
            # (ragged party-disjoint bands fan out into per-segment periods, like
            # the loader/backfill). `disjoint` is pk-ordered, so a segment's bands
            # are too and `bands[0]` (lowest pk) carries the winning min/max nights.
            for seg in segment_card_rules(disjoint).segments:
                bands: tuple[_Band, ...] = seg.rules
                # GAP-059: keep the curated label when the segment's bands all
                # descend from one source period (the common carry); a segment
                # that regrouped bands from different periods has no single
                # name to copy — fall back to the same date-span placeholder
                # the loader and backfill use.
                source_names = {band.period_name for band in bands}
                new_period = RatePeriod.objects.create(
                    plan=new_plan,
                    name=(
                        source_names.pop()
                        if len(source_names) == 1
                        else derive_period_name(seg.date_from, seg.date_to)
                    ),
                    date_from=seg.date_from,
                    date_to=seg.date_to,
                    min_nights=bands[0].min_nights,
                    max_nights=bands[0].max_nights,
                )
                for band in bands:
                    RateBand.objects.create(
                        period=new_period,
                        min_party=band.min_party,
                        max_party=band.max_party,
                        nightly=band.nightly,
                        weekly=band.weekly,
                        is_poa=band.is_poa,
                        is_approved=True,
                        is_locked=False,
                        notes=band.notes,
                    )
        return new_plan
