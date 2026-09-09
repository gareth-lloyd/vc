"""Storage-side companions to hard deletes (no soft delete, so files leak
unless a `post_delete` receiver releases them)."""

from __future__ import annotations

from typing import Any

import structlog
from django.db import transaction
from django.db.models.fields.files import FieldFile

logger = structlog.get_logger(__name__)


def release_stored_file_after_commit(
    field_file: FieldFile, *, log_event: str, **context: Any
) -> None:
    """Queue the stored file's deletion for when the transaction commits.

    `post_delete` fires *inside* the deleting transaction; deleting from
    storage there would (a) run S3 HTTP calls while holding the DB connection
    and (b) destroy the object even if the transaction later rolls back,
    leaving a surviving row with a dangling key. Deferring to `on_commit`
    means storage only changes once the row deletion is durable.

    A storage fault in the callback is logged as `log_event` (with `context`
    and the key) rather than raised: the row is already gone, so nothing the
    caller could do with the exception helps, and an orphaned object beats a
    request that 500s after its work committed. Catches `Exception`, not a
    narrower tuple — S3 transport and credential errors (`BotoCoreError`)
    share no base with `OSError`/`ClientError`. Storage `delete` is a no-op
    for a missing file, so a file-less row never logs.
    """
    if not field_file:
        return
    storage, name = field_file.storage, field_file.name
    if not name:
        return

    def _release() -> None:
        try:
            storage.delete(name)
        except Exception:
            logger.exception(log_event, storage_key=name, **context)

    transaction.on_commit(_release)
