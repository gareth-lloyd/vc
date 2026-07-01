"""Backfill `RatePeriod` rows from existing flat `RateBand`s (GAP-056 Unit 2).

The rebuild flattened dates onto `RateBand`; GAP-056 lifts them onto a
`RatePeriod` date-axis level. This helper reconstructs that level for rows that
predate it: it groups every plan's rules, segments them with the pure
`segment_card_rules` utility, creates one `RatePeriod` per distinct segment, and
points each rule at its covering period. A ragged rule (one a sibling band's
boundary bisects) is *fragmented* — the original keeps its pk on its first
segment; extra fragments are cloned onto the remaining segments.

Callable from both the Unit 2 data migration (historical model classes via
`apps.get_model`) and unit tests (concrete classes): it touches only `.objects`,
plain field reads, `get_or_create`, and `create`, which both satisfy. Idempotent
— a second run finds every rule already period-stamped and does nothing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from pricing.services.segmentation import segment_card_rules

# Fields copied verbatim onto a cloned fragment (everything but identity, dates,
# and the FKs/period set explicitly below).
_FRAGMENT_FIELDS = (
    "min_party",
    "max_party",
    "nightly",
    "weekly",
    "is_poa",
    "is_locked",
    "is_approved",
    "notes",
)


@dataclass(frozen=True)
class BackfillResult:
    periods_created: int = 0
    rules_pointed: int = 0
    fragments_created: int = 0
    orphaned_rules: int = 0


def backfill_plan_periods(rate_period_model: Any, rate_rule_model: Any) -> BackfillResult:
    """Create periods for, and point, every not-yet-migrated rule. Returns counts."""
    pending = list(rate_rule_model.objects.filter(period__isnull=True).select_related("card"))
    rules_by_plan: dict[Any, list[Any]] = defaultdict(list)
    for rule in pending:
        rules_by_plan[rule.card.plan_id].append(rule)

    periods_created = 0
    rules_pointed = 0
    fragments_created = 0
    orphaned = 0

    for plan_id, rules in rules_by_plan.items():
        result = segment_card_rules(rules)

        period_by_span: dict[tuple[Any, Any], Any] = {}
        for seg in result.segments:
            period, was_created = rate_period_model.objects.get_or_create(
                plan_id=plan_id,
                date_from=seg.date_from,
                date_to=seg.date_to,
                defaults={"is_active": True},
            )
            period_by_span[(seg.date_from, seg.date_to)] = period
            periods_created += int(was_created)

        # Segments covering each source rule, in date order (identity-keyed: the
        # segmentation utility groups by `id()` so equal rules stay distinct).
        segs_for_rule: dict[int, list[Any]] = defaultdict(list)
        for seg in result.segments:
            for covered in seg.rules:
                segs_for_rule[id(covered)].append(seg)

        for rule in rules:
            segs = sorted(segs_for_rule.get(id(rule), []), key=lambda s: s.date_from)
            if not segs:
                orphaned += 1  # invalid-span row: no covering segment, leave unpointed
                continue
            first, *rest = segs
            rule.period = period_by_span[(first.date_from, first.date_to)]
            rule.date_from = first.date_from
            rule.date_to = first.date_to
            rule.save()
            rules_pointed += 1
            for index, seg in enumerate(rest, start=1):
                rate_rule_model.objects.create(
                    card_id=rule.card_id,
                    period=period_by_span[(seg.date_from, seg.date_to)],
                    date_from=seg.date_from,
                    date_to=seg.date_to,
                    legacy_id=(f"{rule.legacy_id}#seg{index}" if rule.legacy_id else None),
                    **{field: getattr(rule, field) for field in _FRAGMENT_FIELDS},
                )
                fragments_created += 1

    return BackfillResult(
        periods_created=periods_created,
        rules_pointed=rules_pointed,
        fragments_created=fragments_created,
        orphaned_rules=orphaned,
    )
