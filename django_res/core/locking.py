"""Row-lock helpers for state-machine transitions.

Every transition guard in the codebase has the same shape: check `status`
against an allowed set, then write. Checking the *in-memory* status is not
enough — two concurrent requests (an operator double-click, a webhook retry
racing a manual action) each deserialise their own instance, both pass the
guard, and the transition double-fires: duplicate events, duplicate signals,
duplicate gateway calls.

`refresh_locked` is the shared fix: take `SELECT … FOR UPDATE` on the row and
reload the instance in place *before* the guard runs, so the second caller
serialises behind the first and its guard sees the freshly-committed state.
"""

from __future__ import annotations

from django.db import models


def refresh_locked(instance: models.Model) -> None:
    """Lock this row and reload `instance`'s fields in place.

    Must be called inside `transaction.atomic()` (Postgres releases the lock
    at commit/rollback). One query both locks and refreshes — the locking
    SELECT returns the fresh row.

    Any unsaved in-memory field changes are discarded by the reload, so call
    this at the *top* of a transition method, before mutating fields.
    """
    instance.refresh_from_db(from_queryset=type(instance)._base_manager.select_for_update())
