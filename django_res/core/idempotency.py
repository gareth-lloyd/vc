"""Idempotency helpers for state-mutating services.

Webhooks retry. Operators double-click. Background workers re-deliver
messages. Any service that *creates* a row in response to an external
trigger needs a way to short-circuit when the same trigger arrives twice.

The contract:

- Callers pass an optional `idempotency_key: str | None`.
- When provided, the service looks for an existing row keyed by
  `(scope, idempotency_key)` *before* the write — under the same
  transaction so we collapse concurrent retries.
- If a match is found, return it untouched. Otherwise create the row
  with the key stamped on it.

For models with a `meta` JSONField (`Payment`, `Refund`, `SecurityDeposit`)
the key lives in `meta["idempotency_key"]`. For models without one,
add a dedicated column.

`None` means "no idempotency requested" — proceed unconditionally. This
keeps internal callers (tests, management commands, scheduled jobs)
free of ceremony.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet

IDEMPOTENCY_META_KEY = "idempotency_key"


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
