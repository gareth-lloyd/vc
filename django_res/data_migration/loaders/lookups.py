"""Lookup-table loaders: Region, Currency, NearbyPlaceType, FeatureCategory,
Feature.

Most are pure field renames via DeclarativeLoader. Feature has a special
case: legacy uses a many-to-many `VillaFeaturesCategoryMappings` table, but
the new schema has a single FK; we pick the first mapping per feature.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.utils.text import slugify

from data_migration.base import BaseLoader, LoadReport
from data_migration.declarative import DeclarativeLoader
from data_migration.loaders._util import country_for_legacy_id, legacy_row_deleted
from data_migration.loaders.sentinels import unknown_country
from pricing.models.currency import Currency
from properties.enums import FeatureServiceType
from properties.models.features import Feature, FeatureCategory
from properties.models.geo import NearbyPlaceType, Region
from properties.other_information_catalog import (
    OTHER_INFORMATION_CATEGORY_LEGACY_ID,
    OTHER_INFORMATION_CATEGORY_SLUG,
)


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
        return "SELECT Id, Name, Slug, CountryId, DeletedAt, DeletedBy FROM VillaRegion ORDER BY Id"

    def transform_extra(self, row: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any] | None:
        # `Region.name` is 128 wide; legacy `Name` is nvarchar(500).
        kwargs["name"] = (kwargs.get("name") or "").strip()[:128]
        if not kwargs["name"]:
            return None
        legacy_country_id = row.get("CountryId")
        country = (
            country_for_legacy_id(str(legacy_country_id)) if legacy_country_id is not None else None
        )
        if country is None:
            country = unknown_country()
        kwargs["country"] = country
        # BUG-030 §9: legacy slugs carry accents (`andalucía`); `Region.slug`
        # is a SlugField. An all-non-Latin slug and name (Greek script) fall
        # through to `region-{Id}` — the legacy value is not a valid slug.
        base_slug = slugify((kwargs.get("slug") or "").strip()) or slugify(kwargs["name"])
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

    def __init__(self) -> None:
        super().__init__()
        self._deleted_legacy_ids: set[str] = set()

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
        if str(row["Id"]) == OTHER_INFORMATION_CATEGORY_LEGACY_ID:
            # Pinned: the Features tab, the Zoho partition and the seeding
            # stage all key on this slug, and the live legacy row has been
            # renamed since the checked-in snapshot ("Other Information Tags").
            kwargs["slug"] = OTHER_INFORMATION_CATEGORY_SLUG
        else:
            kwargs["slug"] = slugify(name)[:128] or f"feature-cat-{row['Id']}"
        kwargs["sort_order"] = kwargs.get("sort_order") or 0
        kwargs["is_active"] = bool(kwargs.get("is_active"))
        return kwargs


# BUG-030 §12: legacy `VillaFeatures.ServiceType` is on the `EServiceType`
# scale (Unknown=0 / ContactService=10 / PropertyFeature=20) and every live
# feature stores 20, so it carries nothing. `service_type` derives from the
# category `Code` instead: 50 "Included Features" and 70 "Services On
# Request"; everything else is an amenity.
_SERVICE_TYPE_BY_CATEGORY_CODE = {
    50: FeatureServiceType.INCLUDED_SERVICE,
    70: FeatureServiceType.PAID_ADDON,
}


class FeatureLoader(BaseLoader):
    """Maps VillaFeatures → Feature, picking the first category from
    VillaFeaturesCategoryMappings since the new schema demands a single FK.
    A feature mapped to several categories takes its first mapping (by
    mapping Id) for both the FK and the derived `service_type`.
    """

    name = "feature"
    target_model = Feature
    # One OUTER APPLY yields the FK and the code from the SAME first mapping
    # (two separate TOP 1 subqueries could drift apart); `c.Id` breaks a tie
    # between category rows sharing a Code, and `ORDER BY f.Id` makes a slug
    # collision between live namesakes resolve to the lowest Id, matching
    # the reconcile check's `MIN(t.Id)` twin rule (BUG-029 determinism).
    legacy_query = (
        "SELECT f.Id, f.Name, f.Description, f.FeatureOrder, "
        "cat.Id AS CategoryId, cat.Code AS CategoryCode "
        "FROM VillaFeatures f "
        "OUTER APPLY (SELECT TOP 1 c.Id, c.Code FROM VillaFeaturesCategoryMappings m "
        " JOIN VillaFeaturesCategory c ON c.Code = m.CategoryId "
        " WHERE m.FeatureId = f.Id ORDER BY m.Id, c.Id) cat "
        "WHERE f.DeletedAt IS NULL ORDER BY f.Id"
    )

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
        service_type = _SERVICE_TYPE_BY_CATEGORY_CODE.get(
            row.get("CategoryCode") or 0, FeatureServiceType.AMENITY
        )
        return {
            "name": name[:128],
            "slug": slugify(name)[:128] or f"feature-{row['Id']}",
            "description": (row.get("Description") or "").strip(),
            "service_type": service_type,
            "sort_order": row.get("FeatureOrder") or 0,
            "is_active": True,
            "category": cat,
        }
