"""Room (+ RoomBeds), PropertyImage, PropertyNearbyPlace, and the
Property↔Feature M2M.

Image files themselves are not migrated — we store the legacy filename as
the image-field value so the row exists; the file copy is a separate ops
task.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from data_migration.base import BaseLoader, LoadReport
from properties.enums import ImageKind, RoomPlacement
from properties.models.features import Feature
from properties.models.geo import NearbyPlaceType, PropertyNearbyPlace
from properties.models.images import PropertyImage
from properties.models.property import Property
from properties.models.rooms import Room, RoomBeds


class RoomLoader(BaseLoader):
    name = "room"
    target_model = Room
    legacy_query = (
        "SELECT Id, VillaId, Name, WebsiteDescription, VCNotes, IsEnsuit, SortOrder, "
        "BedDouble, BedTwinDouble, BedTwin, BedSingle, BedBunk, BedSofa, BedChildrens "
        "FROM VillaRooms"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaId") or "")).first()
        if prop is None:
            return None
        name = (row.get("Name") or "").strip()[:128] or f"Room {row['Id']}"
        return {
            "property": prop,
            "name": name,
            "placement": RoomPlacement.MAIN_HOUSE,
            "website_description": (row.get("WebsiteDescription") or "").strip(),
            "vc_notes": (row.get("VCNotes") or "").strip(),
            "is_ensuite": bool(row.get("IsEnsuit")),
            "sort_order": int(row.get("SortOrder") or 0),
        }

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        super()._process_row(row, report)
        legacy_id = row.get(self.legacy_pk_column)
        if legacy_id is None:
            return
        room = Room.objects.filter(legacy_id=str(legacy_id)).first()
        if room is None:
            return
        with transaction.atomic():
            RoomBeds.objects.update_or_create(
                room=room,
                defaults={
                    "double": int(row.get("BedDouble") or 0),
                    "twin_double": int(row.get("BedTwinDouble") or 0),
                    "twin": int(row.get("BedTwin") or 0),
                    "single": int(row.get("BedSingle") or 0),
                    "bunk": int(row.get("BedBunk") or 0),
                    "sofa": int(row.get("BedSofa") or 0),
                    "childrens": int(row.get("BedChildrens") or 0),
                },
            )


class PropertyImageLoader(BaseLoader):
    name = "property_image"
    target_model = PropertyImage
    legacy_query = (
        "SELECT Id, VillaId, Name, Description, IsGallary, IsHero, "
        "IsInterior1, IsInterior2, IsExterior1, IsExterior2, "
        "SortOrder, IsActive FROM VillaPropertyImages"
    )

    def _kind_for(self, row: dict[str, Any]) -> str:
        if row.get("IsHero"):
            return ImageKind.HERO
        if row.get("IsInterior1") or row.get("IsInterior2"):
            return ImageKind.INTERIOR
        if row.get("IsExterior1") or row.get("IsExterior2"):
            return ImageKind.EXTERIOR
        return ImageKind.GALLERY

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaId") or "")).first()
        if prop is None:
            return None
        filename = (row.get("Name") or "").strip()
        if not filename:
            return None
        kind = self._kind_for(row)
        is_active = bool(row.get("IsActive"))
        # Hero uniqueness: demote duplicate active heros to gallery.
        if (
            kind == ImageKind.HERO
            and is_active
            and PropertyImage.objects.filter(
                property=prop,
                kind=ImageKind.HERO,
                is_active=True,
            )
            .exclude(legacy_id=str(row["Id"]))
            .exists()
        ):
            kind = ImageKind.GALLERY
        return {
            "property": prop,
            "image": f"properties/legacy/{filename}",
            "kind": kind,
            "name": filename[:255],
            "description": (row.get("Description") or "").strip(),
            "sort_order": int(row.get("SortOrder") or 0),
            "is_active": is_active,
        }


class NearbyPlaceLoader(BaseLoader):
    name = "nearby_place"
    target_model = PropertyNearbyPlace
    legacy_query = (
        "SELECT n.Id, n.PropertyId, "
        "(SELECT TOP 1 t.Id FROM VillaNearByLocationType t "
        " WHERE t.Code = n.PropertyNearByLocationTypeId) AS TypeId, "
        "n.Name, n.Description, n.Distance "
        "FROM VillaNearBy n"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        prop = Property.objects.filter(legacy_id=str(row.get("PropertyId") or "")).first()
        if prop is None:
            return None
        place_type = NearbyPlaceType.objects.filter(
            legacy_id=str(row.get("TypeId") or ""),
        ).first()
        if place_type is None:
            return None
        name = (row.get("Name") or "").strip()[:255]
        if not name:
            return None
        return {
            "property": prop,
            "place_type": place_type,
            "name": name,
            "distance_km": row.get("Distance") or 0,
            "notes": (row.get("Description") or "").strip(),
        }


class PropertyFeatureMappingLoader(BaseLoader):
    """Property↔Feature M2M. Writes to the auto-through table directly.

    Doesn't need legacy_id on the through model — we resolve both sides and
    rely on the M2M's implicit unique(property, feature) constraint.
    """

    name = "property_feature"
    target_model = Feature  # placeholder; we override _process_row entirely
    # `MIN(MappingOrder)` collapses any duplicate (FeatureId, VillaId) pairs in
    # the legacy data to one row per pair (lowest display position wins) — the
    # new PropertyFeature unique constraint would otherwise reject the dups. The
    # existing GROUP BY already groups by the pair, so MIN is a free aggregate.
    legacy_query = (
        "SELECT FeatureId, VillaId, MIN(MappingOrder) AS MappingOrder "
        "FROM VillaFeaturesMappings GROUP BY FeatureId, VillaId"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        return None  # unused — _process_row overridden

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaId") or "")).first()
        feature = Feature.objects.filter(legacy_id=str(row.get("FeatureId") or "")).first()
        if prop is None or feature is None:
            report.skipped += 1
            return
        # `update_or_create` converges `sort_order` on idempotent re-runs (a
        # cutover-only loader, so no post-go-live user reorder exists to clobber)
        # and is the residual-dup safety net — it updates rather than tripping
        # the unique constraint if the in-SQL MIN dedup ever lets one slip.
        through = Property.features.through
        _, created = through.objects.update_or_create(
            property_id=prop.pk,
            feature_id=feature.pk,
            defaults={"sort_order": int(row.get("MappingOrder") or 0)},
        )
        if created:
            report.created += 1
        else:
            report.updated += 1
