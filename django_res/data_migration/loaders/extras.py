"""Loader: legacy extras catalogue (`VillaSeasonRate WHERE IsExTra = 1`)
→ `pricing.Extra` (GAP-107).

Legacy kept a villa's extras in the rate table, flagged `IsExTra`. The
rows were folded in from the pre-2022 `tblPropertyExtra` with junk
`FromDate`/`ToDate` (the 2022 migration run date) and `CurrencyId = 0`, and
the legacy Extras UI only ever edited `Name` / `Description` / `Price`. So a
ported extra is a **menu item**: no date window, no unit beyond "per stay",
opt-in (`is_mandatory=False`).

Two contracts follow from "staff refine kind/calc/window in the SPA":

- **Design fields are create-only.** A re-run (or `--since` delta) refreshes
  only what legacy can actually change — `name`, `description`, `amount` —
  and never resets `kind`, `calc`, `is_mandatory`, the window, the party
  bounds, `sort_order`, `is_active` or `currency` on an existing row.
- **A full run retires what legacy deleted.** Ported extras absent from a
  full (non-`--since`) result set are set `is_active=False`; a `--since`
  delta cannot see deletions and leaves them alone (CUTOVER.md §4i).

`RateBandLoader` excludes these rows from the rate grid; this loader is the
only reader of them.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog

from data_migration.base import BaseLoader, LoadReport
from data_migration.loaders._util import legacy_currency_for
from pricing.enums import ExtraCalc, ExtraKind
from pricing.models.extra import Extra
from properties.models.property import Property

logger = structlog.get_logger(__name__)

# The only fields a legacy edit can change; everything else is create-only.
_LEGACY_OWNED_FIELDS = ("name", "description", "amount")


class ExtraLoader(BaseLoader):
    name = "extra"
    target_model = Extra
    legacy_pk_column = "ID"
    # Same deletion filter as `RateBandLoader` (its 3805 calibration keys on
    # `DeletedAt IS NULL`); the reconcile check mirrors it.
    legacy_query = (
        "SELECT ID, VillaId, Name, Description, Price, CurrencyId "
        "FROM VillaSeasonRate WHERE DeletedAt IS NULL AND IsExTra = 1"
    )

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        # Dense per-villa rank in legacy creation order, so a ported
        # catalogue sorts 0..n and a staff-created extra (default 0) does not
        # jump ahead of it by thousands. Only consulted at create time.
        rank: dict[Any, int] = {}
        for row in sorted(rows, key=lambda r: (r.get("VillaId") or 0, r.get("ID") or 0)):
            villa = row.get("VillaId")
            row["SortOrder"] = rank.get(villa, 0)
            rank[villa] = row["SortOrder"] + 1
        super()._load_rows(rows, report)
        if self.since:
            return
        seen = {str(r["ID"]) for r in rows if r.get("ID") is not None}
        stale = Extra.objects.filter(legacy_id__isnull=False, is_active=True).exclude(
            legacy_id__in=seen
        )
        retired = 0
        for extra in stale:  # save() loop: Extra is audit-tracked
            extra.is_active = False
            extra.save(update_fields=["is_active", "updated_at"])
            retired += 1
        if retired:
            logger.info("data_migration.extras_retired", retired=retired)

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaId") or "")).first()
        if prop is None:
            return None
        # `CurrencyId` is 0 on every folded extra; the engine filters extras
        # by exact currency match, so resolve the way it does (preferred
        # live plan → settings → EUR) and the extra lands in the currency
        # quotes are built in.
        currency = legacy_currency_for(row, prop)
        if currency is None:
            return None
        legacy_id = row["ID"]
        description = (row.get("Description") or "").strip()
        name = (row.get("Name") or "").strip() or description or f"Extra {legacy_id}"
        return {
            "property": prop,
            "name": name[:128],
            "description": description,
            "kind": ExtraKind.OTHER,
            "calc": ExtraCalc.FIXED_PER_STAY,
            "amount": row.get("Price") or Decimal("0"),
            "currency": currency,
            "is_mandatory": False,
            "commissionable": True,
            "applies_from": None,
            "applies_to": None,
            "min_party": None,
            "max_party": None,
            "is_active": True,
            "sort_order": row.get("SortOrder", 0),
        }

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        legacy_id = row.get(self.legacy_pk_column)
        if legacy_id is None:
            report.skipped += 1
            return
        try:
            kwargs = self.transform(row)
        except Exception as exc:
            report.errors.append((str(legacy_id), repr(exc)))
            return
        if kwargs is None:
            report.skipped += 1
            return
        existing = Extra.objects.filter(legacy_id=str(legacy_id)).first()
        if existing is None:
            Extra.objects.create(legacy_id=str(legacy_id), **kwargs)
            report.created += 1
            return
        for field in _LEGACY_OWNED_FIELDS:
            setattr(existing, field, kwargs[field])
        existing.save(update_fields=[*_LEGACY_OWNED_FIELDS, "updated_at"])
        report.updated += 1
