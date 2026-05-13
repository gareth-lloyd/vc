"""Lookup-table loaders: Region, Currency, PropertyCategory, NearbyPlaceType,
FeatureCategory, Feature.

Most are pure field renames via DeclarativeLoader. Feature has a special
case: legacy uses a many-to-many `VillaFeaturesCategoryMappings` table, but
the new schema has a single FK; we pick the first mapping per feature.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.utils.text import slugify

from data_migration.base import BaseLoader
from data_migration.declarative import DeclarativeLoader
from data_migration.loaders.sentinels import unknown_country
from pricing.models.currency import Currency
from properties.models.features import Feature, FeatureCategory
from properties.models.geo import Country, NearbyPlaceType, Region
from properties.models.property import PropertyCategory


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
        return "SELECT Id, Name, Slug, CountryId FROM VillaRegion"

    def transform_extra(self, row: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any] | None:
        kwargs["name"] = (kwargs.get("name") or "").strip()
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
        kwargs["is_active"] = True
        return kwargs


class CurrencyLoader(DeclarativeLoader):
    name = "currency"
    legacy_table = "VillaCurrency"
    target_model = Currency
    field_map = {
        "Name": "name",
        "Code": "code",
        "Symbol": "symbol",
    }

    def transform_extra(self, row: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any] | None:
        code = (kwargs.get("code") or "").strip().upper()
        if len(code) != 3 or not code.isalpha():
            return None
        # Legacy has duplicate currency rows (multiple "EUR"). Keep the first
        # one we saw; let later legacy_ids point at the same Django row by
        # silently skipping if a different legacy_id already claims the code.
        existing = Currency.objects.filter(code=code).exclude(legacy_id=str(row["Id"])).first()
        if existing is not None:
            return None
        kwargs["code"] = code
        kwargs["name"] = (kwargs.get("name") or "").strip()[:64] or code
        kwargs["symbol"] = (kwargs.get("symbol") or "").strip()[:8]
        kwargs["is_active"] = not bool(row.get("DeletedAt"))
        return kwargs


class PropertyCategoryLoader(DeclarativeLoader):
    name = "property_category"
    legacy_table = "VillaPropertyCategory"
    target_model = PropertyCategory
    field_map = {"Name": "name"}

    def transform_extra(self, row: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any] | None:
        name = (kwargs.get("name") or "").strip()
        if not name:
            return None
        kwargs["name"] = name[:128]
        kwargs["slug"] = slugify(name)[:128] or f"category-{row['Id']}"
        kwargs["is_active"] = True
        return kwargs


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
