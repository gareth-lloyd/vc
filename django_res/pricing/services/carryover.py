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

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import structlog
from django.db import transaction

from core.exceptions import NoRateAvailable
from pricing.models import RateCard, RatePlan, RateRule
from pricing.services.projection import (
    DateMap,
    RateProjectionService,
    keep_calendar_date,
    load_anchor_cards_with_rules,
    projected_rule_fields,
    shift_to_changeover_weekday,
)

logger = structlog.get_logger(__name__)


def _clip_collisions(fields: dict[str, Any], inserted: list[RateRule]) -> dict[str, Any] | None:
    """Nudge a mapped rule off any already-inserted sibling it collides with.

    Date-mapping can collide adjacent source ranges by a day (a leap-year
    range spanning Feb 29 keeps its span while the calendar loses a day), and
    `raterule_no_overlap` would turn that into an `IntegrityError`. Push
    `date_from` past each party-overlapping sibling; `None` (skip the rule)
    when clipping empties the range.
    """
    for prev in inserted:
        if fields["date_from"] > prev.date_to or fields["date_to"] < prev.date_from:
            continue
        if fields["min_party"] > prev.max_party or fields["max_party"] < prev.min_party:
            continue
        fields = {**fields, "date_from": prev.date_to + timedelta(days=1)}
    if fields["date_from"] >= fields["date_to"]:
        return None
    return fields


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
            # Same active-card / approved-rule set the projection quotes, via the
            # shared loader (batched, no per-card query) — so the materialised rows
            # match the guide a quote would have shown, with no dormant inactive
            # cards or unapproved rows carried forward.
            for card, rules in load_anchor_cards_with_rules(anchor):
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
                inserted: list[RateRule] = []
                for rule in sorted(rules, key=lambda r: (r.date_from, r.pk)):
                    fields = projected_rule_fields(rule, year_delta, date_map, factor)
                    clipped = _clip_collisions(fields, inserted)
                    if clipped is None:
                        logger.info(
                            "pricing.carryover.rule_skipped",
                            source_rule_id=rule.pk,
                            reason="date_map_collision_emptied_range",
                        )
                        continue
                    if clipped["date_from"] != fields["date_from"]:
                        logger.info(
                            "pricing.carryover.rule_clipped",
                            source_rule_id=rule.pk,
                            clipped_from=str(clipped["date_from"]),
                        )
                    inserted.append(
                        RateRule.objects.create(
                            card=new_card,
                            is_approved=True,
                            is_locked=False,
                            notes=rule.notes,
                            **clipped,
                        )
                    )
        return new_plan
