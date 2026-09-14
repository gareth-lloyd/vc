"""Regime invariants (GAP-110): DB-constraint names and their HTTP mapping.

A *regime* is a `RatePlan`'s `(property, currency)` bucket. Two database
invariants back it; the serializers pre-check both as 400s with guidance, and
the views wrap their writes in a guard so a racing writer that slips past a
pre-check gets a 409 `RegimeConflict` rather than a 500.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import date, timedelta
from typing import Any

from django.db import IntegrityError, transaction

from core.exceptions import MultiRegimeStay, RegimeConflict
from pricing.models import RatePeriod, RatePlan
from pricing.services.currency import pick_preferred_plan


def _covered_nights(periods: Sequence[RatePeriod], date_from: date, date_to: date) -> int:
    """How many nights of `[date_from, date_to)` `periods` cover (one regime —
    pairwise disjoint by the EXCLUDE, so the clipped spans simply add up)."""
    last_night = date_to - timedelta(days=1)
    return sum(
        (min(period.date_to, last_night) - max(period.date_from, date_from)).days + 1
        for period in periods
    )


def select_regime_plan(
    property: Any,
    touching: Sequence[RatePeriod],
    date_from: date,
    date_to: date,
) -> RatePlan:
    """The one plan that prices `[date_from, date_to)`, inferred from the
    active periods `touching` the stay (each with `plan` loaded).

    Across currencies (a currency-less quote): the currency whose periods
    cover the **most** nights is preferred (so a stay straddling a currency
    switch prices in the currency that owns more of it, never on the other
    currency's fallback); among the tied, the settings currency wins, then
    the lowest plan pk (`pick_preferred_plan`). Within the chosen currency at
    most one plan may touch the stay — a GROSS and a NET regime both touching
    it raise `MultiRegimeStay` rather than blend two price bases.
    """
    by_currency: dict[int, list[RatePeriod]] = {}
    for period in touching:
        by_currency.setdefault(period.currency_id, []).append(period)
    if len(by_currency) > 1:
        coverage = {
            currency_id: _covered_nights(periods, date_from, date_to)
            for currency_id, periods in by_currency.items()
        }
        best = max(coverage.values())
        # Keyed by the *period's* stamped currency (not `plan.currency_id`)
        # so a plan whose currency drifted from its periods' stamp still
        # resolves to a period set rather than a KeyError.
        candidate_plans: dict[int, RatePlan] = {}
        currency_of_plan: dict[int, int] = {}
        for currency_id, periods in by_currency.items():
            if coverage[currency_id] != best:
                continue
            for period in periods:
                candidate_plans[period.plan.pk] = period.plan
                currency_of_plan[period.plan.pk] = currency_id
        preferred = pick_preferred_plan(list(candidate_plans.values()), property)
        assert preferred is not None  # candidates are never empty here
        chosen = by_currency[currency_of_plan[preferred.pk]]
    else:
        chosen = next(iter(by_currency.values()))
    plans = {period.plan.pk: period.plan for period in chosen}
    if len(plans) > 1:
        named = ", ".join(
            f'"{plan.name}" (#{plan.pk})' for plan in sorted(plans.values(), key=lambda p: p.pk)
        )
        code = next(iter(chosen)).currency.code
        raise MultiRegimeStay(
            f"Stay {date_from}..{date_to} at {getattr(property, 'name', property)} is priced "
            f"by more than one {code} rate plan: {named}. Adjust the periods so a single "
            "plan covers the whole stay."
        )
    return next(iter(plans.values()))


# `RatePeriod` EXCLUDE partitioned on the stamped (property, currency).
_PERIOD_OVERLAP_CONSTRAINT = "rateperiod_no_overlap"
_PERIOD_OVERLAP_MESSAGE = (
    "Another rate period for this property and currency already covers part of "
    "these dates; reload and pick dates that are free."
)


def is_constraint_violation(exc: IntegrityError, name: str) -> bool:
    """True iff `exc` came from the named constraint.

    Prefers psycopg's `Diagnostic.constraint_name` (robust to message
    formatting, locale, deferred constraints); falls back to a substring
    check on the rendered message (same pattern as `reservations.Booking`).
    """
    diag = getattr(getattr(exc, "__cause__", None), "diag", None)
    if getattr(diag, "constraint_name", None) == name:
        return True
    return name in str(exc)


@contextmanager
def _regime_conflict_guard(constraint: str, message: str) -> Iterator[None]:
    """Map an `IntegrityError` from `constraint` to `RegimeConflict` (409).

    The write runs inside `atomic()`: the audit trail's `pre_save` receiver
    inserts the `AuditLog` row *before* the model row, so without a
    transaction a raced constraint violation would autocommit an orphan audit
    row for a period that never existed. Under an outer transaction this is a
    savepoint, which also keeps the connection usable after the rollback. Any
    other `IntegrityError` is a genuine error and re-raises untouched.
    """
    try:
        with transaction.atomic():
            yield
    except IntegrityError as exc:
        if not is_constraint_violation(exc, constraint):
            raise
        raise RegimeConflict(message) from exc


def period_overlap_guard() -> AbstractContextManager[None]:
    """Guard a `RatePeriod` write against `rateperiod_no_overlap`."""
    return _regime_conflict_guard(_PERIOD_OVERLAP_CONSTRAINT, _PERIOD_OVERLAP_MESSAGE)


# `RatePlan` partial unique on (property, currency, price_basis) where active.
_PLAN_UNIQUE_CONSTRAINT = "rateplan_one_active_per_regime"
_PLAN_UNIQUE_MESSAGE = (
    "Another active rate plan for this property, currency and price basis was "
    "just created; reload and add periods to it instead."
)


def plan_regime_guard() -> AbstractContextManager[None]:
    """Guard a `RatePlan` write against `rateplan_one_active_per_regime`."""
    return _regime_conflict_guard(_PLAN_UNIQUE_CONSTRAINT, _PLAN_UNIQUE_MESSAGE)
