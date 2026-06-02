"""Small shared helpers for the legacy loaders."""

from __future__ import annotations

from typing import Any


def legacy_quotation_no(row: dict[str, Any]) -> int | None:
    """Parse the legacy `QuotationNo`, returning a positive int or `None`.

    `0`, NULL, negative, and non-numeric values all map to `None`, so the
    quotation and booking loaders interpret a missing/sentinel `QuotationNo`
    identically (avoiding the `QVC0` / `VC0` references a bare `int()` would
    have produced).
    """
    raw = row.get("QuotationNo")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None
