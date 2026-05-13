"""Loader: legacy VillaCountry → properties.Country.

Legacy columns of interest (per ResSystem/Database/Data/VillaCountry.cs):
- Id              → legacy_id
- Name            → name
- ShortName1      → iso2  (legacy stored ISO-2 here)
- ShortName2      → iso3  (legacy stored ISO-3 here)
- TaxRate         → default_tax_rate
- CountryOrder    → sort_order
- IsActive        → is_active

The 0009 migration pre-seeds the 249 canonical iso2 rows with no
legacy_id, so this loader merges legacy rows onto them by iso2 (or by
django-countries name lookup when ShortName1/2 are blank). Rows we
can't identify map onto `unknown_country()` so downstream FKs still
resolve.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from data_migration.base import BaseLoader, LoadReport
from data_migration.loaders.sentinels import unknown_country
from properties.models.geo import Country


def _resolve_iso2(name: str, raw_iso2: str) -> str | None:
    if raw_iso2 and len(raw_iso2) == 2 and raw_iso2.isalpha():
        return raw_iso2
    # Fallback: name match against django-countries.
    if not name:
        return None
    from django_countries import countries as dc_countries

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
        "Code, CountryOrder, IsActive, TaxRate "
        "FROM VillaCountry"
    )

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        legacy_id = row.get(self.legacy_pk_column)
        if legacy_id is None:
            report.skipped += 1
            return
        legacy_id_str = str(legacy_id)

        name = (row.get("Name") or "").strip()
        raw_iso2 = (row.get("ShortName1") or "").strip().upper()
        iso2 = _resolve_iso2(name, raw_iso2)

        dial_raw = row.get("Code")
        dial_code = f"+{dial_raw}" if dial_raw else ""
        tax_rate = row.get("TaxRate") or Decimal("0")
        sort_order = row.get("CountryOrder") or 0
        is_active = bool(row.get("IsActive"))

        if iso2 is None:
            # Map this legacy id onto the unknown sentinel. Multiple legacy
            # ids may collapse onto it; we keep whichever was attached last.
            sentinel = unknown_country()
            if sentinel.legacy_id != legacy_id_str:
                sentinel.legacy_id = legacy_id_str
                sentinel.save(update_fields=["legacy_id"])
                report.updated += 1
            else:
                report.skipped += 1
            return

        # Merge onto the canonical row by iso2 (idempotent: writes the
        # legacy_id back so future Region FK lookups succeed).
        from django_countries import countries as dc_countries

        canonical_iso3 = dc_countries.alpha3(iso2) or iso2 + "_"
        defaults: dict[str, Any] = {
            "iso3": canonical_iso3,
            "dial_code": dial_code,
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

        # If another legacy id already claims this iso2, leave it alone.
        if existing.legacy_id and existing.legacy_id != legacy_id_str:
            report.skipped += 1
            return

        for k, v in defaults.items():
            setattr(existing, k, v)
        existing.save()
        report.updated += 1
