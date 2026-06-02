"""Shared legacy-parse helpers (GAP-006 remediation)."""

from __future__ import annotations

import pytest

from data_migration.loaders._util import legacy_quotation_no


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1805, 1805),
        ("1805", 1805),
        (0, None),
        ("0", None),
        (-3, None),
        (None, None),
        ("not-a-number", None),
    ],
)
def test_legacy_quotation_no(raw: object, expected: int | None) -> None:
    assert legacy_quotation_no({"QuotationNo": raw}) == expected


def test_legacy_quotation_no_missing_key() -> None:
    assert legacy_quotation_no({}) is None
