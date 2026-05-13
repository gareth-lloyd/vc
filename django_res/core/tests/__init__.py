"""Shared test helpers for `django_res` apps.

Helpers exported here are stable test utilities — anything that grows
beyond a few lines or pulls in heavy fixtures should move into its own
`core/tests/helpers/<name>.py` and be re-exported here.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection
from django.test.utils import CaptureQueriesContext

__all__ = ["assert_max_queries"]


@contextmanager
def assert_max_queries(limit: int) -> Iterator[CaptureQueriesContext]:
    """Assert the wrapped block runs at most `limit` SQL queries.

    Use to pin a viewset against N+1 regressions: invoke the endpoint
    once with one row and once with many rows, both inside the context
    manager — query count must stay flat.

        with assert_max_queries(6):
            api_client.get("/api/v1/payments")

    On failure the message lists every captured SQL statement so the
    offending query is obvious without re-running under a debugger.
    """
    with CaptureQueriesContext(connection) as ctx:
        yield ctx
    if len(ctx.captured_queries) > limit:
        sql_dump = "\n".join(f"  {i + 1}. {q['sql']}" for i, q in enumerate(ctx.captured_queries))
        raise AssertionError(
            f"Expected at most {limit} queries, got {len(ctx.captured_queries)}:\n{sql_dump}"
        )
