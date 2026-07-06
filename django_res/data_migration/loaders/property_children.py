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
from data_migration.placement_parsing import parse_placement
from properties.enums import ImageKind
from properties.models.features import Feature
from properties.models.geo import NearbyPlaceType, PropertyNearbyPlace
from properties.models.images import PropertyImage
from properties.models.property import Property
from properties.models.rooms import Room, RoomBeds


class RoomLoader(BaseLoader):
    name = "room"
    target_model = Room
    # GAP-065: LEFT JOIN so rooms with a NULL PlacementId still load; the raw
    # placement string is preserved verbatim in `placement_note` (no-loss
    # guarantee) and parsed into the two location axes.
    legacy_query = (
        "SELECT r.Id, r.VillaId, r.Name, r.WebsiteDescription, r.VCNotes, r.IsEnsuit, "
        "r.SortOrder, r.BedDouble, r.BedTwinDouble, r.BedTwin, r.BedSingle, r.BedBunk, "
        "r.BedSofa, r.BedChildrens, p.Name AS PlacementName "
        "FROM VillaRooms r LEFT JOIN VillaRoomsPlacement p ON p.Id = r.PlacementId"
    )
    # With two tables in the FROM, an unqualified `UpdatedAt` from
    # `_apply_since` would be ambiguous SQL.
    since_column = "r.UpdatedAt"

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaId") or "")).first()
        if prop is None:
            return None
        name = (row.get("Name") or "").strip()[:128] or f"Room {row['Id']}"
        placement_note = (row.get("PlacementName") or "").strip()[:255]
        placement, floor = parse_placement(placement_note)
        return {
            "property": prop,
            "name": name,
            "placement": placement,
            "floor": floor,
            "placement_note": placement_note,
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
    # `VillaPropertyImagesDescription` is one row per villa (not per image)
    # whose Interior1/2 + Exterior1/2 texts caption the images flagged
    # IsInterior1/2 + IsExterior1/2 on the same villa. The MAX(Id) subselect
    # pins the join to a single description row: the table is unique per
    # VillaId except for junk VillaId=0 duplicates, which would otherwise
    # fan the images out.
    legacy_query = (
        "SELECT i.Id, i.VillaId, i.Name, i.Description, i.IsGallary, i.IsHero, "
        "i.IsInterior1, i.IsInterior2, i.IsExterior1, i.IsExterior2, "
        "i.SortOrder, i.IsActive, "
        "d.Interior1 AS SlotInterior1, d.Interior2 AS SlotInterior2, "
        "d.Exterior1 AS SlotExterior1, d.Exterior2 AS SlotExterior2 "
        "FROM VillaPropertyImages i "
        "LEFT JOIN VillaPropertyImagesDescription d ON d.Id = ("
        "SELECT MAX(d2.Id) FROM VillaPropertyImagesDescription d2 "
        "WHERE d2.VillaId = i.VillaId)"
    )

    # Slot flag → villa-level caption column, in `_kind_for` precedence order.
    _caption_slots: tuple[tuple[str, str], ...] = (
        ("IsInterior1", "SlotInterior1"),
        ("IsInterior2", "SlotInterior2"),
        ("IsExterior1", "SlotExterior1"),
        ("IsExterior2", "SlotExterior2"),
    )

    def _slot_caption(self, row: dict[str, Any]) -> str:
        """First non-blank slot text whose flag is set on this image."""
        for flag, slot in self._caption_slots:
            if row.get(flag):
                text = (row.get(slot) or "").strip()
                if text:
                    return text
        return ""

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
            # Precedence: the image's own Description wins over the villa-level
            # slot caption. In the dump this never bites — none of the 1,226
            # flagged images carries its own Description — but a post-dump edit
            # to the per-image field should not be shadowed.
            "description": (row.get("Description") or "").strip() or self._slot_caption(row),
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
