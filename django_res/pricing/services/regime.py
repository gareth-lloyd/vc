"""Regime invariants (GAP-110): DB-constraint names and their HTTP mapping.

A *regime* is a `RatePlan`'s `(property, currency)` bucket. Two database
invariants back it; the serializers pre-check both as 400s with guidance, and
the views wrap their writes in a guard so a racing writer that slips past a
pre-check gets a 409 `RegimeConflict` rather than a 500.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager

from django.db import IntegrityError, transaction

from core.exceptions import RegimeConflict

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
