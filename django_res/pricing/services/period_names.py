"""Placeholder-name derivation for ``RatePeriod`` rows (GAP-059).

``RatePeriod.name`` is a compulsory operator label, but three writers have no
meaningful name to draw from — the legacy loader (legacy has no period-name
column), the migration backfill (which inlines a copy of this logic per the
no-app-imports migration convention) and the carry-forward service. They all
persist the same deterministic date-span placeholder so re-runs are
byte-identical and an operator can rename at leisure.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable

_MONTHS_ABBR = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)  # fmt: skip

# En dash, matching the SPA's `formatWeekRangeCompact` output. Kept as an
# escape so the intentional non-ASCII glyph doesn't trip RUF001.
_EN_DASH = "\u2013"


def derive_period_name(date_from: datetime.date, date_to: datetime.date) -> str:
    """Compact inclusive date span: "3-21 Jul" / "3 Jul-21 Aug" (en-dashed).

    Years appear only when the span crosses a year boundary
    ("27 Dec 2026-3 Jan 2027"); a single-day span renders as one date.
    Deliberately locale-independent (fixed English month abbreviations, not
    ``django.utils.formats.date_format``): the value is persisted, and loader
    idempotency requires it to be byte-identical across re-runs regardless of
    the active language.
    """
    from_month = _MONTHS_ABBR[date_from.month - 1]
    to_month = _MONTHS_ABBR[date_to.month - 1]
    if date_from.year != date_to.year:
        return (
            f"{date_from.day} {from_month} {date_from.year}"
            f"{_EN_DASH}{date_to.day} {to_month} {date_to.year}"
        )
    if date_from.month != date_to.month:
        return f"{date_from.day} {from_month}{_EN_DASH}{date_to.day} {to_month}"
    if date_from.day != date_to.day:
        return f"{date_from.day}{_EN_DASH}{date_to.day} {from_month}"
    return f"{date_from.day} {from_month}"


def uniform_or_derived_name(
    names: Iterable[str], date_from: datetime.date, date_to: datetime.date
) -> str:
    """GAP-059 rule for naming a flattened period from its bands' parentage.

    Keep the curated operator label when every band descends from one source
    period (the common, no-collision carry); a period that regrouped bands
    from different source periods has no single name to copy, so fall back to
    the `derive_period_name` date-span placeholder. Shared by every BUG-016
    flattener consumer that persists or projects periods, so a projected
    period and its materialised twin always carry the same label.
    """
    unique = set(names)
    if len(unique) == 1:
        return unique.pop()
    return derive_period_name(date_from, date_to)
