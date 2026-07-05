"""Property + Location + Capacity + Settings + Description loaders.

The Property loader is the big one: a single VillaMaster row creates five
Django rows (Property + four 1:1 children). Description is multi-row per
property — one per non-empty section.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils.text import slugify

from data_migration.base import BaseLoader, LoadReport
from data_migration.loaders.sentinels import (
    unknown_country,
    unknown_region,
)
from pricing.models.currency import Currency
from properties.enums import (
    AvailabilityDefault,
    DescriptionSection,
    PrefilledChangeOverDay,
    PriceBasis,
    PropertyChannel,
    PropertyStatus,
)
from properties.models.capacity import PropertyCapacity
from properties.models.descriptions import PropertyDescription
from properties.models.features import Collection, CollectionMembership
from properties.models.geo import Region
from properties.models.location import PropertyLocation
from properties.models.property import Property, PropertyCategory
from properties.models.settings import PropertySettings
from properties.services.location import location_defaults

_PROPERTY_STATUS_MAP = {
    # VillaStatus.Id → PropertyStatus
    1: PropertyStatus.ACTIVE,
    2: PropertyStatus.DRAFT,
    3: PropertyStatus.ARCHIVED,
    4: PropertyStatus.ARCHIVED,
}

# Legacy changeover columns (`VillaMaster.SettingChangeoverDayId`,
# `VillaConfigPropertyDefault.ChangeOverDay`) store `ChangeOverDays.Code`,
# NOT the table's identity Id — the Blazor selects bind `Item1 = [Code]`
# (`PropertyService.GetChangeOverDays` selects `[Code], [Name]`). Seeded
# codes: -1 = Open/flexible, 0 = Sunday, 1 = Monday .. 6 = Saturday.
_DAY_MAP = {
    -1: PrefilledChangeOverDay.ANY,
    0: PrefilledChangeOverDay.SUN,
    1: PrefilledChangeOverDay.MON,
    2: PrefilledChangeOverDay.TUE,
    3: PrefilledChangeOverDay.WED,
    4: PrefilledChangeOverDay.THU,
    5: PrefilledChangeOverDay.FRI,
    6: PrefilledChangeOverDay.SAT,
}


def _decimal_or_none(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


class PropertyLoader(BaseLoader):
    """VillaMaster -> Property (+ Location + Capacity + Settings + Descriptions).

    All five children are written in the same transaction. Property is the
    canonical legacy_id holder; children use property as their PK so they
    inherit identity from it.
    """

    name = "property"
    target_model = Property
    legacy_query = (
        "SELECT Id, Name, DisplayName, Slug, OverView, HouseRules, "
        "FeatureDescription, RoomDescription, Notes, "
        "LocalityRegion, LocalityTown, AddressLine1, AddressLine2, AddressLine3, "
        "PostCode, LicenceNumber, Latitude, Longitude, "
        "Category, Channel, Guests, AdditionalGuests, Bedrooms, Ensuites, "
        "Bathrooms, Size, "
        "RegionId, ViilaStatus, "
        "SettingAvailabilityStatusId, SettingIsBookingsRequirePreApproval, "
        "SettingPricesEnteredTypeId, SettingCurrencyId, "
        "SettingCheckInTime, SettingCheckOutTime, SettingChangeoverDayId, "
        "SettingMinNightsRental, SettingMinNightsRentalNote "
        "FROM VillaMaster WHERE DeletedAt IS NULL"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        name = (row.get("Name") or "").strip()[:255]
        if not name:
            return None

        region = Region.objects.filter(legacy_id=str(row.get("RegionId") or "")).first()
        category = (
            PropertyCategory.objects.filter(legacy_id=str(row["Category"])).first()
            if row.get("Category")
            else None
        )
        if region is None:
            region = self._sentinel_region()
        if category is None:
            # Fall back to first available; create a sentinel if none exist.
            category = PropertyCategory.objects.first()
            if category is None:
                category, _ = PropertyCategory.objects.get_or_create(
                    name="Uncategorised",
                    defaults={"slug": "uncategorised", "is_active": True},
                )

        # Slug: legacy may be missing/duplicate; suffix with legacy_id.
        legacy_slug = (row.get("Slug") or "").strip() or slugify(name)
        slug = f"{legacy_slug[:200]}-{row['Id']}"[:255]

        return {
            "name": name,
            "display_name": (row.get("DisplayName") or name)[:255],
            "slug": slug,
            "licence_number": (row.get("LicenceNumber") or "").strip()[:128],
            "status": _PROPERTY_STATUS_MAP.get(
                row.get("ViilaStatus") or 0,
                PropertyStatus.DRAFT,
            ),
            "channel": PropertyChannel.DIRECT,
            "category": category,
            "region": region,
        }

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        super()._process_row(row, report)
        legacy_id = row.get(self.legacy_pk_column)
        if legacy_id is None:
            return
        prop = Property.objects.filter(legacy_id=str(legacy_id)).first()
        if prop is None:
            return
        with transaction.atomic():
            self._write_location(prop, row)
            self._write_capacity(prop, row)
            self._write_settings(prop, row)
            self._write_descriptions(prop, row)

    def _sentinel_region(self) -> Region:
        # 1:N rows in the source data hit this fallback; resolving the
        # sentinel once per loader saves ~3 queries per missing-FK property.
        if not hasattr(self, "_sentinel_region_cache"):
            self._sentinel_region_cache = unknown_region(unknown_country())
        return self._sentinel_region_cache

    def _write_location(self, prop: Property, row: dict[str, Any]) -> None:
        PropertyLocation.objects.update_or_create(
            property=prop,
            defaults={
                **location_defaults(prop),
                "address_line_1": (row.get("AddressLine1") or "")[:255],
                "address_line_2": (row.get("AddressLine2") or "")[:255],
                "address_line_3": (row.get("AddressLine3") or "")[:255],
                "post_code": (row.get("PostCode") or "")[:32],
                "locality_town": (row.get("LocalityTown") or "")[:128],
                "locality_region": (row.get("LocalityRegion") or "")[:128],
                "latitude": _decimal_or_none(row.get("Latitude")),
                "longitude": _decimal_or_none(row.get("Longitude")),
            },
        )

    def _write_capacity(self, prop: Property, row: dict[str, Any]) -> None:
        size = _decimal_or_none(row.get("Size"))
        PropertyCapacity.objects.update_or_create(
            property=prop,
            defaults={
                "guests": int(row.get("Guests") or 0),
                "additional_guests": int(row.get("AdditionalGuests") or 0),
                "bedrooms": int(row.get("Bedrooms") or 0),
                "ensuites": int(row.get("Ensuites") or 0),
                "bathrooms": int(row.get("Bathrooms") or 0),
                "size_sqm": size,
            },
        )

    def _write_settings(self, prop: Property, row: dict[str, Any]) -> None:
        # NOT `or 0` — 0 is a real code (Sunday), only NULL means unset.
        day_code = row.get("SettingChangeoverDayId")
        changeover = _DAY_MAP.get(day_code) if day_code is not None else None
        currency = (
            Currency.objects.filter(legacy_id=str(row["SettingCurrencyId"])).first()
            if row.get("SettingCurrencyId")
            else None
        )
        PropertySettings.objects.update_or_create(
            property=prop,
            defaults={
                "availability_default": AvailabilityDefault.AVAILABLE,
                "bookings_require_pre_approval": bool(
                    row.get("SettingIsBookingsRequirePreApproval"),
                ),
                "requires_enquiry_first": False,
                "currency": currency,
                "check_in_time": row.get("SettingCheckInTime"),
                "check_out_time": row.get("SettingCheckOutTime"),
                "changeover_day": changeover,
                "min_nights_rental": int(row.get("SettingMinNightsRental") or 1),
                "min_nights_rental_note": (row.get("SettingMinNightsRentalNote") or "")[:1000],
                "prices_entered_as": PriceBasis.GROSS,
            },
        )

    def _write_descriptions(self, prop: Property, row: dict[str, Any]) -> None:
        # Per 09-departures.md: WebsiteDescription/OverView->OVERVIEW;
        # HouseRules->HOUSE_RULES; FeatureDescription+RoomDescription
        # concatenated->VILLA_INFO.
        sections: dict[str, str] = {}
        if overview := (row.get("OverView") or "").strip():
            sections[DescriptionSection.OVERVIEW] = overview
        if rules := (row.get("HouseRules") or "").strip():
            sections[DescriptionSection.HOUSE_RULES] = rules
        feat = (row.get("FeatureDescription") or "").strip()
        rooms = (row.get("RoomDescription") or "").strip()
        if feat or rooms:
            joined = "\n\n".join(p for p in (feat, rooms) if p)
            sections[DescriptionSection.VILLA_INFO] = joined
        if notes := (row.get("Notes") or "").strip():
            sections[DescriptionSection.FURTHER_INFO] = notes

        for section, body in sections.items():
            PropertyDescription.objects.update_or_create(
                property=prop,
                section=section,
                defaults={
                    "body": body,
                    "legacy_id": f"{row['Id']}-{section}",
                },
            )


class CollectionLoader(BaseLoader):
    name = "collection"
    target_model = Collection
    legacy_query = (
        "SELECT Id, Name, Description, IsActive=1 FROM VillaCollection WHERE DeletedAt IS NULL"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        name = (row.get("Name") or "").strip()[:128]
        if not name:
            return None
        slug = slugify(name)[:120] + f"-{row['Id']}"
        return {
            "name": name,
            "slug": slug[:128],
            "description": (row.get("Description") or "").strip(),
            "is_active": True,
        }


class CollectionMembershipLoader(BaseLoader):
    name = "collection_membership"
    target_model = CollectionMembership
    legacy_query = (
        "SELECT Id, VillaMasterId, VillaCollectionId, VillaOrder, Description "
        "FROM VillaCollectionsMappings"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaMasterId") or "")).first()
        coll = Collection.objects.filter(legacy_id=str(row.get("VillaCollectionId") or "")).first()
        if prop is None or coll is None:
            return None
        # Legacy has multiple mapping rows for the same (collection, property)
        # — keep the first one we saw.
        existing = (
            CollectionMembership.objects.filter(property=prop, collection=coll)
            .exclude(legacy_id=str(row["Id"]))
            .exists()
        )
        if existing:
            return None
        return {
            "property": prop,
            "collection": coll,
            "sort_order": int(row.get("VillaOrder") or 0),
            "description": (row.get("Description") or "").strip(),
        }
