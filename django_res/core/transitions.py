"""The one state-transition primitive (BUG-015).

Every status-driven model moves the same way: lock the row and reload it
(`core.locking.refresh_locked`), check the edge against the entity's
allowed-transitions table, write the new status plus any fields that move
with it in one `save(update_fields=…)` (so the `pre_save` audit trail sees
it), then write the aggregate's own event row — all inside one transaction.

Tables are `<ENTITY>_ALLOWED_TRANSITIONS` in the owning app's `enums.py`,
keyed by from-status, terminals listed explicitly as empty sets. A status
missing from the table is treated as terminal.

Deliberately *not* here: signals and other side effects. Each entity keeps
firing them where it does today (Q-024 is still open on whether money side
effects belong on signals), so wrappers send them after calling `transition`.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from typing import Any

from django.db import models, transaction

from core.exceptions import InvalidTransition
from core.locking import refresh_locked

TransitionTable = Mapping[str, Collection[str]]


def can_transition(instance: models.Model, to: str, *, table: TransitionTable) -> bool:
    """Whether the table allows `instance`'s *in-memory* status to move to `to`.

    For pre-filters (skip a cascade that would be refused). It does not lock —
    the transition itself re-checks under lock.
    """
    return to in table.get(getattr(instance, "status"), ())  # noqa: B009


def assert_allowed(instance: models.Model, to: str, *, table: TransitionTable) -> None:
    """Raise `InvalidTransition` unless the table allows the move to `to`.

    Checks in-memory status, so call it after `refresh_locked` when the guard
    must see committed state (wrappers that validate before `transition`).
    """
    if not can_transition(instance, to, table=table):
        status = getattr(instance, "status")  # noqa: B009
        raise InvalidTransition(status, to, allowed=sorted(table.get(status, ())))


def transition(
    instance: models.Model,
    to: str,
    *,
    table: TransitionTable,
    extra_updates: dict[str, Any] | None = None,
    record: Callable[[str, str], None] | None = None,
) -> str:
    """Lock, guard, move `instance` to `to`, and record it. Returns the prior status.

    `extra_updates` are field values written in the same UPDATE as the status.
    `record(prev, to)` writes the aggregate's event row inside the transaction,
    so a failed write rolls the status back with it.

    Any in-memory changes made before the call are discarded by the lock
    refresh; compute derived values after locking (see `refresh_locked`).
    If the move fails after the guard, the instance's status and `extra_updates`
    fields are restored to their locked values, so it doesn't claim a move
    this call rolled back.
    """
    extras = extra_updates or {}
    prev: str | None = None
    snapshot: dict[str, Any] = {}
    try:
        with transaction.atomic():
            refresh_locked(instance)
            assert_allowed(instance, to, table=table)
            prev = getattr(instance, "status")  # noqa: B009
            snapshot = {field: getattr(instance, field) for field in extras}
            setattr(instance, "status", to)  # noqa: B010
            for field, value in extras.items():
                setattr(instance, field, value)
            instance.save(update_fields=["status", "updated_at", *extras])
            if record is not None:
                record(prev, to)
    except BaseException:
        # Covers errors raised at this block's own commit too (deferred FK
        # checks). An outer transaction's later rollback is the caller's to handle.
        if prev is not None:
            setattr(instance, "status", prev)  # noqa: B010
            for field, value in snapshot.items():
                setattr(instance, field, value)
        raise
    return prev
