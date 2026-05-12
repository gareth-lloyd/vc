"""Read-only cursor against the legacy SQL Server connection.

The legacy DB is wired in `settings.base` only when `LEGACY_DATABASE_URL` is
set, so importing this module is always cheap, but calling `legacy_cursor()`
without the env var raises a clear error.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from django.db import connections


@contextmanager
def legacy_cursor() -> Iterator[Any]:
    if "legacy" not in connections.databases:
        raise RuntimeError(
            "Legacy DB not configured. Set LEGACY_DATABASE_URL and rerun.",
        )
    with connections["legacy"].cursor() as cursor:
        yield cursor


def rows_as_dicts(cursor: Any) -> Iterator[dict[str, Any]]:
    """Yield each row from a cursor as a column-name → value dict."""
    columns = [col[0] for col in cursor.description]
    for row in cursor:
        yield dict(zip(columns, row, strict=True))
