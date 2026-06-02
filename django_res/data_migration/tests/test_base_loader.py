"""Per-row isolation in `BaseLoader._load_rows` (GAP-006 remediation).

A single bad legacy row (e.g. a write-time unique collision) must be recorded
in `report.errors` and skipped without aborting the rows that follow. Before
this, the whole loop ran in one `transaction.atomic()`, so one IntegrityError
poisoned the entire import.
"""

from __future__ import annotations

from typing import Any

import pytest

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
