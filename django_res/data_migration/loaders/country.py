"""Loader: legacy VillaCountry → properties.Country.

Legacy columns of interest (per ResSystem/Database/Data/VillaCountry.cs):
- Id              → legacy_id
- Name            → name
- ShortName1      → iso2  (legacy stored ISO-2 here; validated against
                    ISO-3166 with `UK` → `GB`, else the name decides —
                    BUG-030 §6)
- ShortName2      → iso3  (legacy stored ISO-3 here)
- Code            → (not loaded: an ordering/lookup integer, NOT a calling
                    code — Greece is 300; BUG-030 §5)
- TaxRate         → default_tax_rate
- CountryOrder    → sort_order
- IsActive        → is_active (AND NOT deleted — GAP-107: `DeletedAt` /
                    `DeletedBy` retire the row rather than skipping it, so
                    FKs onto it still resolve; the exception is a deleted
                    row whose iso2 another legacy row already claims — that
                    duplicate is skipped and its `CountryId` consumers fall
                    to `unknown_country()`, unless `LEGACY_COUNTRY_ALIASES`
                    names it, as it does England 24 → GB)

The 0009 migration pre-seeds the 249 canonical iso2 rows with no
legacy_id, so this loader merges legacy rows onto them by iso2 (or by
django-countries name lookup when ShortName1/2 are blank). Rows we
can't identify map onto `unknown_country()` so downstream FKs still
resolve.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog

from data_migration.base import BaseLoader, LoadReport
from data_migration.loaders._util import LEGACY_ISO2_ALIASES, legacy_row_deleted
from data_migration.loaders.sentinels import unknown_country
from properties.models.geo import Country

logger = structlog.get_logger(__name__)


def _resolve_iso2(name: str, raw_iso2: str) -> str | None:
    from django_countries import countries as dc_countries

    # BUG-030 §6: only a real ISO-3166 code counts (legacy "England" is
    # stored as `UK`, and any other two letters used to mint a bogus row).
    # `alpha2` also normalises an alpha-3 / numeric spelling ("GRC", "826")
    # to the alpha-2 the seed is keyed on; unknown → "" → the name decides.
    iso2 = dc_countries.alpha2(LEGACY_ISO2_ALIASES.get(raw_iso2, raw_iso2))
    if iso2:
        return iso2
    # Fallback: name match against django-countries.
    if not name:
        return None
    needle = name.strip().lower()
    for iso2, canonical_name in dc_countries:
        if str(canonical_name).strip().lower() == needle:
            return iso2
    return None


class CountryLoader(BaseLoader):
    name = "country"
    target_model = Country
    legacy_query = (
        "SELECT Id, Name, ShortName1, ShortName2, "
        "CountryOrder, IsActive, TaxRate, DeletedAt, DeletedBy "
        "FROM VillaCountry ORDER BY Id"
    )

    def __init__(self) -> None:
        super().__init__()
        # legacy ids of the soft-deleted rows in the current run — lets a
        # live row displace an iso2 claim a deleted twin made on an earlier
        # run (see `_process_row`).
        self._deleted_legacy_ids: set[str] = set()

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        # Live rows claim an iso2 before deleted duplicates (stable sort, so
        # Id order is otherwise preserved), so a deleted twin can never
        # stamp its legacy_id onto the ISO seed ahead of the live row.
        self._deleted_legacy_ids = {
            str(r.get(self.legacy_pk_column)) for r in rows if legacy_row_deleted(r)
        }
        super()._load_rows(sorted(rows, key=legacy_row_deleted), report)

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        legacy_id = row.get(self.legacy_pk_column)
        if legacy_id is None:
            report.skipped += 1
            return
        legacy_id_str = str(legacy_id)

        name = (row.get("Name") or "").strip()
        raw_iso2 = (row.get("ShortName1") or "").strip().upper()
        iso2 = _resolve_iso2(name, raw_iso2)

        tax_rate = row.get("TaxRate") or Decimal("0")
        sort_order = row.get("CountryOrder") or 0
        deleted = legacy_row_deleted(row)
        is_active = bool(row.get("IsActive")) and not deleted

        if iso2 is None:
            # Junk row with no resolvable ISO code: make sure the unknown
            # sentinel exists (regions fall back to it) but never re-point its
            # `legacy_id` — "last junk row wins" was order-dependent (BUG-029).
            unknown_country()
            logger.info("data_migration.country_without_iso_skipped", legacy_id=legacy_id_str)
            report.skipped += 1
            return

        # Merge onto the canonical row by iso2 (idempotent: writes the
        # legacy_id back so future Region FK lookups succeed).
        from django_countries import countries as dc_countries

        canonical_iso3 = dc_countries.alpha3(iso2) or iso2 + "_"
        defaults: dict[str, Any] = {
            "iso3": canonical_iso3,
            "default_tax_rate": tax_rate,
            "sort_order": sort_order,
            "is_active": is_active,
            "legacy_id": legacy_id_str,
        }
        if name:
            defaults["name"] = name

        existing = Country.objects.filter(iso2=iso2).first()
        if existing is None:
            defaults.setdefault("name", name or iso2)
            Country.objects.create(iso2=iso2, **defaults)
            report.created += 1
            return

        # If another legacy id already claims this iso2, leave it alone —
        # unless the claimant is a soft-deleted twin (stamped by a run that
        # predates GAP-107, or a legacy delete-and-recreate) and this row is
        # live: then the live row takes the seed over. A deleted row never
        # displaces anyone.
        if existing.legacy_id and existing.legacy_id != legacy_id_str:
            stale_claim = existing.legacy_id in self._deleted_legacy_ids
            if deleted or not stale_claim:
                report.skipped += 1
                return

        for k, v in defaults.items():
            setattr(existing, k, v)
        existing.save()
        report.updated += 1
