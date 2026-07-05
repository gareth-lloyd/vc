"""Backfill `RatePeriod` rows from flat pre-GAP-056 `RateRule`s (migration 0013 only).

The rebuild flattened dates onto `RateBand`; GAP-056 lifts them onto a
`RatePeriod` date-axis level. This helper reconstructs that level for rows that
predate it: it flattens every plan's rules to the disjoint (date x party) grid,
creates one `RatePeriod` per flat period, and points each rule at its covering
period — the original rule keeps its pk on its first surviving cell; extra
cells are cloned as `#seg{n}` fragments.

Callable ONLY with pricing 0013's historical models (`apps.get_model`): the
rules here still carry a `card` FK, their own `date_from`/`date_to`, and a
nullable `period` — all gone from the HEAD models since GAP-056 dropped
`RateCard` — so tests drive it through `MigrationExecutor` at the 0013 state.

Conflict policy is the shared BUG-016 flattener (`flatten_rate_grid`,
precedence = lowest pk): pre-0013 party-colliding rows resolve by precedence
instead of being tolerated as shared-period collisions — a fully shadowed
loser stays unpointed (counted in `shadowed_rules`), a clipped loser keeps its
uncovered brackets. Empty-table replays (fresh test DBs, already-applied prod)
are unaffected. Idempotent for the migration's own use — a second run finds
every rule already period-stamped and does nothing. Caveat for direct callers:
a shadowed loser stays `period IS NULL`, so re-running over that leftover
WITHOUT its winners in `pending` would flatten it unopposed and resurrect it;
unreachable through 0013 itself (the migration is atomic — a crash rolls the
whole backfill back).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from django.db import connection

from pricing.services.flattening import SourceBand, flatten_rate_grid

# Fields copied verbatim onto a cloned fragment. Identity, dates, the party
# bracket, and the card/period FKs are set explicitly from the flat cell.
_FRAGMENT_FIELDS = (
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
    shadowed_rules: int = 0


def backfill_plan_periods(rate_period_model: Any, rate_rule_model: Any) -> BackfillResult:
    """Create periods for, and point, every not-yet-migrated rule. Returns counts."""
    pending = list(rate_rule_model.objects.filter(period__isnull=True).select_related("card"))
    if pending and connection.vendor == "postgresql":
        # 0013 runs this inside its atomic migration transaction, with the
        # CREATE INDEX for the new `period` FK column still queued as deferred
        # SQL. Fragment INSERTs below would queue INITIALLY DEFERRED FK checks,
        # and Postgres refuses CREATE INDEX on a table with pending trigger
        # events — so fire the checks per-statement instead. Outside a
        # transaction (direct re-runs) this is a harmless no-op.
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    rules_by_plan: dict[Any, list[Any]] = defaultdict(list)
    for rule in pending:
        rules_by_plan[rule.card.plan_id].append(rule)

    periods_created = 0
    rules_pointed = 0
    fragments_created = 0
    orphaned = 0
    shadowed = 0

    for plan_id, rules in rules_by_plan.items():
        result = flatten_rate_grid(
            SourceBand(
                date_from=rule.date_from,
                date_to=rule.date_to,
                min_party=rule.min_party,
                max_party=rule.max_party,
                precedence=(rule.pk,),
                payload=rule,
            )
            for rule in rules
        )
        orphaned += len(result.invalid_spans)  # degenerate span: leave unpointed
        shadowed += len(result.dropped_sources)  # lost every cell to a lower pk

        for flat_period in result.periods:
            period, was_created = rate_period_model.objects.get_or_create(
                plan_id=plan_id,
                date_from=flat_period.date_from,
                date_to=flat_period.date_to,
                defaults={"is_active": True},  # no name: 0013 predates the name CHECK
            )
            periods_created += int(was_created)

            for band in flat_period.bands:
                rule = band.source.payload
                if band.fragment_index == 0:
                    rule.period = period
                    rule.date_from = flat_period.date_from
                    rule.date_to = flat_period.date_to
                    # The bracket may have been clipped by a winning sibling.
                    rule.min_party = band.min_party
                    rule.max_party = band.max_party
                    rule.save()
                    rules_pointed += 1
                else:
                    rate_rule_model.objects.create(
                        card_id=rule.card_id,
                        period=period,
                        date_from=flat_period.date_from,
                        date_to=flat_period.date_to,
                        min_party=band.min_party,
                        max_party=band.max_party,
                        legacy_id=(
                            f"{rule.legacy_id}#seg{band.fragment_index}" if rule.legacy_id else None
                        ),
                        **{field: getattr(rule, field) for field in _FRAGMENT_FIELDS},
                    )
                    fragments_created += 1

    return BackfillResult(
        periods_created=periods_created,
        rules_pointed=rules_pointed,
        fragments_created=fragments_created,
        orphaned_rules=orphaned,
        shadowed_rules=shadowed,
    )
