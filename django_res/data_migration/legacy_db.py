"""Read-only cursor against the legacy SQL Server.

Direct pymssql connection rather than going through Django's `connections`
framework, because we never need ORM access to the legacy schema and pymssql
ships a wheel that doesn't require MS ODBC driver installation on the host.

Configuration: set `LEGACY_DATABASE_URL=mssql://user:password@host:port/dbname`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import unquote, urlparse

import pymssql


@contextmanager
def legacy_cursor() -> Iterator[Any]:
    url = os.environ.get("LEGACY_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Legacy DB not configured. Set LEGACY_DATABASE_URL "
            "(mssql://user:password@host:port/dbname) and rerun.",
        )

    parsed = urlparse(url)
    if parsed.scheme not in {"mssql", "sqlserver"}:
        raise RuntimeError(
            f"LEGACY_DATABASE_URL scheme must be mssql:// or sqlserver:// (got {parsed.scheme!r})"
        )
    if not (parsed.hostname and parsed.username and parsed.path):
        raise RuntimeError("LEGACY_DATABASE_URL must include host, user, and database")

    conn = pymssql.connect(
        server=parsed.hostname,
        port=str(parsed.port or 1433),
        user=unquote(parsed.username),
        password=unquote(parsed.password or ""),
        database=parsed.path.lstrip("/"),
    )
    try:
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()
    finally:
        conn.close()


def rows_as_dicts(cursor: Any) -> Iterator[dict[str, Any]]:
    columns = [col[0] for col in cursor.description]
    for row in cursor:
        yield dict(zip(columns, row, strict=True))
