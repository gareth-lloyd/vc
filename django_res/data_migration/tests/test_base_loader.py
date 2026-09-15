"""Per-row isolation in `BaseLoader._load_rows` (GAP-006 remediation).

A single bad legacy row (e.g. a write-time unique collision) must be recorded
in `report.errors` and skipped without aborting the rows that follow. Before
this, the whole loop ran in one `transaction.atomic()`, so one IntegrityError
poisoned the entire import.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest

from data_migration import base as base_module
from data_migration.base import BaseLoader, LoadReport
from pricing.models.currency import Currency


class _ThrowawayLoader(BaseLoader):
    """Upserts Currency rows keyed on legacy_id; `code` is unique, so two rows
    sharing a code collide at write time (not in transform)."""

    name = "throwaway"
    target_model = Currency
    legacy_query = ""

    def transform(self, row: dict[str, Any]) -> dict[str, Any]:
        return {"code": row["code"], "name": row["name"], "symbol": "x"}


@pytest.mark.django_db
def test_load_rows_isolates_a_failing_write() -> None:
    loader = _ThrowawayLoader()
    report = LoadReport(loader="throwaway")
    rows = [
        {"Id": 1, "code": "AAA", "name": "Alpha"},
        {"Id": 2, "code": "AAA", "name": "Beta"},  # duplicate code -> IntegrityError on write
        {"Id": 3, "code": "CCC", "name": "Gamma"},
    ]

    loader._load_rows(rows, report)

    # The bad row is recorded, the others still commit.
    assert Currency.objects.filter(code="AAA").count() == 1
    assert Currency.objects.filter(code="CCC").count() == 1
    assert report.created == 2
    assert len(report.errors) == 1
    assert report.errors[0][0] == "2"


class _EmptyLegacyCursor:
    description = [("Id",)]
    queries: list[str]

    def __init__(self) -> None:
        self.queries = []

    def execute(self, sql: str) -> None:
        self.queries.append(sql)

    def __iter__(self) -> Iterator[tuple[Any, ...]]:
        return iter(())


class _RatePlanWritingLoader(BaseLoader):
    """Writes a RatePlan + RateBand straight from `_load_rows` — the shape of
    the pricing loaders, whose saves would each enqueue a summary rebuild."""

    name = "rate_plan_writer"
    target_model = Currency
    legacy_query = "SELECT 1"

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        from pricing.factories import RateBandFactory

        RateBandFactory()
        report.created += 1


@pytest.mark.django_db
def test_load_enqueues_no_pricing_summary_rebuild(
    monkeypatch: pytest.MonkeyPatch, django_capture_on_commit_callbacks: Any
) -> None:
    """GAP-108: a full `loadlegacy` must not enqueue one Celery rebuild per
    loaded rate row — `rebuild_summaries` backfills the cache once, after."""

    @contextmanager
    def _fake_cursor() -> Iterator[_EmptyLegacyCursor]:
        yield _EmptyLegacyCursor()

    monkeypatch.setattr(base_module, "legacy_cursor", _fake_cursor)

    with (
        patch("pricing.signals.rebuild_summary_task.delay") as delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        report = _RatePlanWritingLoader().load()

    assert report.created == 1
    delay.assert_not_called()
