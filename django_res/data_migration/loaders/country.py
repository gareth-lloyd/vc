"""Loader: legacy VillaCountry → properties.Country.

Legacy columns of interest (per ResSystem/Database/Data/VillaCountry.cs):
- Id              → legacy_id
- Name            → name
- ShortName1      → iso2  (legacy stored ISO-2 here)
- ShortName2      → iso3  (legacy stored ISO-3 here)
- TaxRate         → default_tax_rate
- CountryOrder    → sort_order
- IsActive        → is_active

Rows missing both ISO codes are skipped — the new schema enforces unique
non-null iso2/iso3, and a country we can't identify is unusable.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from data_migration.base import BaseLoader
from properties.models.geo import Country


class CountryLoader(BaseLoader):
    name = "country"
    target_model = Country
    legacy_query = (
        "SELECT Id, Name, ShortName1, ShortName2, "
        "Code, CountryOrder, IsActive, TaxRate "
        "FROM VillaCountry"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        iso2 = (row.get("ShortName1") or "").strip().upper()
        iso3 = (row.get("ShortName2") or "").strip().upper()
        if not iso2 or not iso3:
            return None

        dial_raw = row.get("Code")
        dial_code = f"+{dial_raw}" if dial_raw else ""

        return {
            "name": (row.get("Name") or "").strip(),
            "iso2": iso2,
            "iso3": iso3,
            "dial_code": dial_code,
            "default_tax_rate": row.get("TaxRate") or Decimal("0"),
            "sort_order": row.get("CountryOrder") or 0,
            "is_active": bool(row.get("IsActive")),
        }
