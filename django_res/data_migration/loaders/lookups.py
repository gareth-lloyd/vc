"""Lookup-table loaders: Region, Currency, NearbyPlaceType, FeatureCategory,
Feature.

Most are pure field renames via DeclarativeLoader. Feature has a special
case: legacy uses a many-to-many `VillaFeaturesCategoryMappings` table, but
the new schema has a single FK; we pick the first mapping per feature.
"""

from __future__ import annotations

from typing import Any, ClassVar

import structlog
from django.utils.text import slugify

from data_migration.base import BaseLoader, LoadReport
from data_migration.declarative import DeclarativeLoader
from data_migration.loaders._util import legacy_changed_since_sql, legacy_row_deleted
from data_migration.loaders.sentinels import unknown_country
from pricing.models.currency import Currency
from properties.models.features import Feature, FeatureCategory
from properties.models.geo import Country, NearbyPlaceType, Region

logger = structlog.get_logger(__name__)


class RegionLoader(DeclarativeLoader):
    name = "region"
    legacy_table = "VillaRegion"
    target_model = Region
    field_map = {
        "Name": "name",
        "Slug": "slug",
    }
    # Country is resolved manually in transform_extra so we can fall back to
    # the unknown sentinel when the legacy CountryId doesn't match anything.
    fk_map: ClassVar[dict[str, tuple[type[Any], str]]] = {}

    @property
    def legacy_query(self) -> str:  # type: ignore[override]
        # GAP-107: deleted regions still load (villas, enquiries and people
        # may point at them) but as `is_active=False` — GAP-102's "retired:
        # readable, not selectable".
        return "SELECT Id, Name, Slug, CountryId, DeletedAt, DeletedBy FROM VillaRegion"

    def _apply_since(self, query: str) -> str:
        if not self.since:
            return query
        return f"{query} WHERE {legacy_changed_since_sql(self.since)}"

    def transform_extra(self, row: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any] | None:
        # `Region.name` is 128 wide; legacy `Name` is nvarchar(500).
        kwargs["name"] = (kwargs.get("name") or "").strip()[:128]
        if not kwargs["name"]:
            return None
        legacy_country_id = row.get("CountryId")
        country = (
            Country.objects.filter(legacy_id=str(legacy_country_id)).first()
            if legacy_country_id is not None
            else None
        )
        if country is None:
            country = unknown_country()
        kwargs["country"] = country
        base_slug = (kwargs.get("slug") or "").strip() or slugify(kwargs["name"])
        kwargs["slug"] = (base_slug[:120] + f"-{row['Id']}") if base_slug else f"region-{row['Id']}"
        # Inactive when the region's own row is deleted OR its country is not
        # selectable: CountryLoader (registered first) retires deleted and
        # `IsActive = 0` countries, and an unresolvable `CountryId` lands on
        # the (inactive) unknown sentinel. One source of truth for the
        # country's state — the loaded row — rather than re-deriving it here.
        kwargs["is_active"] = not legacy_row_deleted(row) and country.is_active
        return kwargs


class CurrencyLoader(BaseLoader):
    """VillaCurrency -> Currency, one row per ISO code.

    Legacy holds duplicate codes: EUR Id 2 (soft-deleted) and Id 3 (live,
    the default every settings/rate/booking row references). Same claim
    rules as CountryLoader (GAP-107): deleted rows load retired, live rows
    claim a code before deleted twins, and a live row displaces a deleted
    twin's earlier claim (BUG-028).
    """

    name = "currency"
    target_model = Currency
    legacy_query = "SELECT Id, Name, Code, Symbol, DeletedAt, DeletedBy FROM VillaCurrency"

    def __init__(self, since: str | None = None) -> None:
        super().__init__(since)
        self._deleted_legacy_ids: set[str] = set()

    def _apply_since(self, query: str) -> str:
        # VillaCurrency has no UpdatedAt/UpdateAt column, so there is nothing
        # to delta on; the table is tiny, so `--since` reloads it in full.
        if self.since:
            logger.warning("data_migration.currency_since_full_reload", since=str(self.since))
        return query

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        # Live rows first (stable sort; not in SQL — see CountryLoader).
        self._deleted_legacy_ids = {
            str(r.get(self.legacy_pk_column)) for r in rows if legacy_row_deleted(r)
        }
        super()._load_rows(sorted(rows, key=legacy_row_deleted), report)

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        legacy_id = row.get(self.legacy_pk_column)
        code = (row.get("Code") or "").strip().upper()
        if legacy_id is None or len(code) != 3 or not code.isalpha():
            report.skipped += 1
            return
        legacy_id_str = str(legacy_id)
        deleted = legacy_row_deleted(row)

        existing = Currency.objects.filter(code=code).first()
        # Another legacy id already owns this code: leave it, unless it is a
        # deleted twin's stale claim and this row is live.
        if existing is not None and existing.legacy_id and existing.legacy_id != legacy_id_str:
            stale_claim = existing.legacy_id in self._deleted_legacy_ids
            if deleted or not stale_claim:
                report.skipped += 1
                return

        fields = {
            "name": (row.get("Name") or "").strip()[:64] or code,
            "symbol": (row.get("Symbol") or "").strip()[:8],
            "is_active": not deleted,
            "legacy_id": legacy_id_str,
        }
        if existing is None:
            Currency.objects.create(code=code, **fields)
            report.created += 1
            return
        for k, v in fields.items():
            setattr(existing, k, v)
        existing.save()
        report.updated += 1


class NearbyPlaceTypeLoader(DeclarativeLoader):
    name = "nearby_place_type"
    legacy_table = "VillaNearByLocationType"
    target_model = NearbyPlaceType
    field_map = {"Name": "name"}

    def transform_extra(self, row: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any] | None:
        name = (kwargs.get("name") or "").strip()
        if not name:
            return None
        kwargs["name"] = name[:128]
        kwargs["icon"] = ""
        return kwargs


class FeatureCategoryLoader(DeclarativeLoader):
    name = "feature_category"
    legacy_table = "VillaFeaturesCategory"
    target_model = FeatureCategory
    field_map = {
        "Name": "name",
        "IsActive": "is_active",
        "Code": "sort_order",
    }

    def transform_extra(self, row: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any] | None:
        name = (kwargs.get("name") or "").strip()
        if not name:
            return None
        kwargs["name"] = name[:128]
        kwargs["slug"] = slugify(name)[:128] or f"feature-cat-{row['Id']}"
        kwargs["sort_order"] = kwargs.get("sort_order") or 0
        kwargs["is_active"] = bool(kwargs.get("is_active"))
        return kwargs


class FeatureLoader(BaseLoader):
    """Maps VillaFeatures → Feature, picking the first category from
    VillaFeaturesCategoryMappings since the new schema demands a single FK.
    """

    name = "feature"
    target_model = Feature
    legacy_query = (
        "SELECT f.Id, f.Name, f.Description, f.ServiceType, f.FeatureOrder, "
        "(SELECT TOP 1 c.Id FROM VillaFeaturesCategoryMappings m "
        " JOIN VillaFeaturesCategory c ON c.Code = m.CategoryId "
        " WHERE m.FeatureId = f.Id ORDER BY m.Id) AS CategoryId "
        "FROM VillaFeatures f WHERE f.DeletedAt IS NULL"
    )

    _service_type_map = {
        1: "amenity",
        2: "included_service",
        3: "paid_addon",
    }

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        name = (row.get("Name") or "").strip()
        if not name:
            return None
        cat_id = row.get("CategoryId")
        if cat_id is None:
            return None
        cat = FeatureCategory.objects.filter(legacy_id=str(cat_id)).first()
        if cat is None:
            return None
        service_type_id = row.get("ServiceType") or 0
        return {
            "name": name[:128],
            "slug": slugify(name)[:128] or f"feature-{row['Id']}",
            "description": (row.get("Description") or "").strip(),
            "service_type": self._service_type_map.get(service_type_id, "amenity"),
            "sort_order": row.get("FeatureOrder") or 0,
            "is_active": True,
            "category": cat,
        }
