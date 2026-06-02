"""On-demand promotion of a projected year into editable rate rows.

The demoted carryover verb. Lazy projection (`pricing.services.projection`) serves
every next-year *quote* without writing anything; this service exists for the
moment staff want **editable** rows for a year — an owner has returned real
numbers, or they want to hand-tune the guide before confirming. It clones the
anchor year forward into real `RatePlan` / `RateCard` / `RateRule` rows, reusing
the same date-map + uplift the projection uses, so the materialised rows match the
guide a quote would have shown.

This is deliberately **not** a Celery beat task: nothing rolls the whole portfolio
forward speculatively. It is invoked per-property, on demand, from the admin action
or the carry-forward endpoint.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction

from core.exceptions import NoRateAvailable
from pricing.models import RateCard, RatePlan, RateRule
from pricing.services.projection import (
    DateMap,
    RateProjectionService,
    apply_uplift,
    keep_calendar_date,
    map_range,
    shift_to_changeover_weekday,
)


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

        target_from = date(target_year, 1, 1)
        target_to = date(target_year, 12, 31)
        anchor = RateProjectionService.find_anchor_plan(property, currency, target_from, target_to)
        if anchor is None:
            raise NoRateAvailable(
                f"No prior RatePlan to carry forward for property "
                f"{getattr(property, 'pk', '?')} currency {currency.code} into {target_year}"
            )

        year_delta = target_year - anchor.effective_from.year
        factor = Decimal("1") + uplift

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
                inclusion=anchor.inclusion,
                notes=f"Carried forward from plan #{anchor.pk} ({anchor.effective_from.year}).",
            )
            for card in RateCard.objects.filter(plan=anchor).order_by("sort_order", "pk"):
                new_card = RateCard.objects.create(
                    plan=new_plan,
                    name=card.name,
                    description=card.description,
                    min_nights=card.min_nights,
                    max_nights=card.max_nights,
                    sort_order=card.sort_order,
                    is_active=card.is_active,
                    notes=card.notes,
                )
                for rule in RateRule.objects.filter(card=card):
                    new_from, new_to = map_range(rule.date_from, rule.date_to, year_delta, date_map)
                    RateRule.objects.create(
                        card=new_card,
                        date_from=new_from,
                        date_to=new_to,
                        min_party=rule.min_party,
                        max_party=rule.max_party,
                        priority=rule.priority,
                        nightly=apply_uplift(rule.nightly, factor),
                        weekly=apply_uplift(rule.weekly, factor),
                        is_poa=rule.is_poa,
                        is_approved=rule.is_approved,
                        is_locked=False,
                        notes=rule.notes,
                    )
        return new_plan
