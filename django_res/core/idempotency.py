"""Idempotency helpers for state-mutating services.

Webhooks retry. Operators double-click. Background workers re-deliver
messages. Any service that *creates* a row in response to an external
trigger needs a way to short-circuit when the same trigger arrives twice.

The contract:

- Callers pass an optional `idempotency_key: str | None`.
- When provided, the service looks for an existing row keyed by
  `(scope, idempotency_key)` *before* the write.
- If a match is found, return it untouched. Otherwise create the row
  with the key stamped on it.

The pre-check alone is check-then-create and NOT race-proof: under READ
COMMITTED, two concurrent calls can both see no row and both create. Every
adopting model therefore needs a DB backstop — a partial unique index over
the same scope the service queries — so the losing racer fails loudly with
`IntegrityError` instead of silently duplicating (FG-010). References:
`refund_idempotency_key_unique_per_booking`,
`payment_idempotency_key_unique_per_booking_purpose`,
`booking_one_per_quotation_line` (natural-key variant).

For models with a `meta` JSONField (`Payment`, `Refund`, `SecurityDeposit`)
the key lives in `meta["idempotency_key"]`. For models without one,
add a dedicated column + `UniqueConstraint` (see
`reservations.OwnerBlock.idempotency_key`).

`None` means "no idempotency requested" — proceed unconditionally. This
keeps internal callers (tests, management commands, scheduled jobs)
free of ceremony.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError

from core.exceptions import IdempotencyConflict

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.db.models import Model, QuerySet

IDEMPOTENCY_META_KEY = "idempotency_key"


@contextmanager
def integrity_conflict_guard(idempotency_key: str | None, message: str) -> Iterator[None]:
    """Map the FG-010 race loser's `IntegrityError` to a 409 conflict.

    Views wrap the service call: two racing requests with the same key both
    pass the service's check-then-create pre-check under READ COMMITTED, and
    the loser trips the model's partial-unique backstop. Keyless requests
    can't trip it (blank keys are excluded from every backstop's condition),
    so their `IntegrityError` is a genuine error and re-raises untouched.
    """
    try:
        yield
    except IntegrityError as exc:
        if idempotency_key is None:
            raise
        raise IdempotencyConflict(message) from exc


def find_by_meta_key[ModelT: Model](
    queryset: QuerySet[ModelT],
    idempotency_key: str | None,
) -> ModelT | None:
    """Return the first row in `queryset` whose `meta["idempotency_key"]`
    matches, or `None` when no key was supplied or no row matches.

    Scope the queryset before calling: pass
    `Payment.objects.filter(booking=booking)` rather than
    `Payment.objects.all()`. Idempotency keys are unique *per logical
    operation context*, not globally — a guest's retried deposit and an
    owner's refund could legitimately share a key string.
    """
    if not idempotency_key:
        return None
    return queryset.filter(**{f"meta__{IDEMPOTENCY_META_KEY}": idempotency_key}).first()


def find_by_key[ModelT: Model](
    queryset: QuerySet[ModelT],
    idempotency_key: str | None,
) -> ModelT | None:
    """`find_by_meta_key`'s twin for models with a dedicated key column.

    Returns the first row in `queryset` whose `idempotency_key` column
    matches, or `None` when no key was supplied or no row matches. The
    column default is `""` (blank = "no idempotency requested"), so a
    falsy key never matches the sea of keyless rows.

    As with the meta variant, scope the queryset to the logical operation
    context before calling (e.g. `RatePlan.objects.filter(property=prop)`) —
    and match the model's partial-unique backstop *exactly*, including any
    status condition the partial index carries. A pre-check broader than the
    backstop can match rows the index deliberately excludes (e.g. OwnerBlock's
    is scoped to APPROVED so cancelled blocks don't stop a re-import) and
    wrongly short-circuit a creation the constraint would have allowed.
    """
    if not idempotency_key:
        return None
    return queryset.filter(idempotency_key=idempotency_key).first()


def stamp_meta(meta: dict[str, Any] | None, idempotency_key: str | None) -> dict[str, Any]:
    """Return a fresh `meta` dict with `idempotency_key` stamped on it.

    No-op when `idempotency_key` is `None`. Returns a *new* dict so
    callers can pass it straight to `.create()` without mutating a
    shared default.
    """
    new_meta = dict(meta or {})
    if idempotency_key:
        new_meta[IDEMPOTENCY_META_KEY] = idempotency_key
    return new_meta
