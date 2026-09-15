"""Room (+ RoomBeds), PropertyImage, PropertyNearbyPlace, and the
Property↔Feature M2M.

Image files themselves are not migrated — we store the legacy filename as
the image-field value so the row exists; the file copy is a separate ops
task.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.db import transaction

from data_migration.base import BaseLoader, LoadReport
from data_migration.loaders._util import legacy_active_sql
from data_migration.placement_parsing import parse_placement
from properties.enums import ImageKind
from properties.models.features import Feature
from properties.models.geo import NearbyPlaceType, PropertyNearbyPlace
from properties.models.images import PropertyImage
from properties.models.property import Property
from properties.models.rooms import Room, RoomBeds

logger = structlog.get_logger(__name__)


class RoomLoader(BaseLoader):
    name = "room"
    target_model = Room
    # GAP-065: LEFT JOIN so rooms with a NULL PlacementId still load; the raw
    # placement string is preserved verbatim in `placement_note` (no-loss
    # guarantee) and parsed into the two location axes. GAP-108: inactive
    # rooms are soft-deleted in ResProd (`vw_VillaRooms`).
    legacy_query = (
        "SELECT r.Id, r.VillaId, r.Name, r.WebsiteDescription, r.VCNotes, r.IsEnsuit, "
        "r.SortOrder, r.BedDouble, r.BedTwinDouble, r.BedTwin, r.BedSingle, r.BedBunk, "
        "r.BedSofa, r.BedChildrens, p.Name AS PlacementName "
        "FROM VillaRooms r LEFT JOIN VillaRoomsPlacement p ON p.Id = r.PlacementId "
        f"WHERE {legacy_active_sql('r.')}"
    )

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
        "WHERE d2.VillaId = i.VillaId) "
        # Hero de-duplication keeps the first active hero processed (BUG-029).
        "ORDER BY i.VillaId, i.Id"
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
        " WHERE t.Code = n.PropertyNearByLocationTypeId ORDER BY t.Id) AS TypeId, "
        "n.Name, n.Description, n.Distance "
        # GAP-108: inactive places are soft-deleted in ResProd
        # (`vw_PropertyNearByLocationType`).
        f"FROM VillaNearBy n WHERE {legacy_active_sql('n.')}"
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


def _normalised_feature_name(name: object) -> str:
    # Same shape `FeatureLoader` stores (`strip()[:128]`), so a long legacy
    # name keys the same as its loaded twin. The reconcile T-SQL uses
    # `LOWER(LTRIM(RTRIM(Name)))` on the full name: it strips spaces only and
    # folds case by collation, so tabs/NBSP and non-ASCII case can diverge —
    # GAP-108 itemises any such row on the live dump.
    return str(name or "").strip()[:128].lower()


def _legacy_id_sort_key(legacy_id: str) -> tuple[int, int | str]:
    return (0, int(legacy_id)) if legacy_id.isdigit() else (1, legacy_id)


def _feature_twins_by_name() -> dict[str, str]:
    """`{normalised name: legacy_id}` over the loaded `Feature` rows, the
    lowest legacy_id winning a name. `FeatureLoader` runs first, so "loaded"
    already means live, named and categorised (a catalog tag stamped with a
    legacy id — `sync_other_information_tags` — also counts as a twin)."""
    twins: dict[str, str] = {}
    for raw_legacy_id, name in Feature.objects.filter(legacy_id__isnull=False).values_list(
        "legacy_id", "name"
    ):
        legacy_id = str(raw_legacy_id)
        key = _normalised_feature_name(name)
        if key and (
            key not in twins or _legacy_id_sort_key(legacy_id) < _legacy_id_sort_key(twins[key])
        ):
            twins[key] = legacy_id
    return twins


class PropertyFeatureMappingLoader(BaseLoader):
    """Property↔Feature M2M. Writes to the auto-through table directly.

    Doesn't need legacy_id on the through model — we resolve both sides and
    rely on the M2M's implicit unique(property, feature) constraint.

    BUG-030 §11: 457 live villa → soft-deleted feature links used to be
    dropped because `FeatureLoader` skips deleted features. 41 of the 53
    deleted features have a live twin by normalised name (55 "Sitting room"
    → 299, on 242 villas), so `_load_rows` remaps a deleted feature to the
    loaded twin of the same name and then dedupes `(villa, feature)` keeping
    the lowest `MappingOrder`. A deleted feature with no twin still skips,
    logged as `data_migration.deleted_feature_unmapped`. The remap lives in
    Python (not T-SQL) so it is testable without SQL Server; the reconcile
    check's legacy side applies the same rule in one derived table.
    """

    name = "property_feature"
    target_model = Feature  # placeholder; we override _process_row entirely
    # `MIN(MappingOrder)` collapses any duplicate (FeatureId, VillaId) pairs in
    # the legacy data to one row per pair (lowest display position wins) — the
    # new PropertyFeature unique constraint would otherwise reject the dups.
    # The feature's name and deletion ride along for the remap above. LEFT
    # JOIN: a mapping whose FeatureId has no VillaFeatures row (no FK in
    # legacy) still reaches `_process_row` and is counted as skipped. GAP-108:
    # an inactive MAPPING is soft-deleted in ResProd (`fn_get_feature_by_villa`)
    # and filtered, unlike a deleted feature, which is remapped.
    legacy_query = (
        "SELECT m.FeatureId, m.VillaId, MIN(m.MappingOrder) AS MappingOrder, "
        "f.Name AS FeatureName, f.DeletedAt AS FeatureDeletedAt "
        "FROM VillaFeaturesMappings m "
        "LEFT JOIN VillaFeatures f ON f.Id = m.FeatureId "
        f"WHERE {legacy_active_sql('m.')} "
        "GROUP BY m.FeatureId, m.VillaId, f.Name, f.DeletedAt"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        return None  # unused — _process_row overridden

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        super()._load_rows(self._remap_deleted_features(rows), report)

    @staticmethod
    def _remap_deleted_features(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        twins: dict[str, str] | None = None
        resolved: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            if row.get("FeatureDeletedAt") is not None:
                if twins is None:
                    twins = _feature_twins_by_name()
                twin = twins.get(_normalised_feature_name(row.get("FeatureName")))
                if twin is None:
                    logger.info(
                        "data_migration.deleted_feature_unmapped",
                        feature_id=str(row.get("FeatureId")),
                        feature_name=str(row.get("FeatureName") or "").strip(),
                        villa_id=str(row.get("VillaId")),
                    )
                else:
                    row = {**row, "FeatureId": twin}
            key = (str(row.get("VillaId") or ""), str(row.get("FeatureId") or ""))
            current = resolved.get(key)
            if current is None or int(row.get("MappingOrder") or 0) < int(
                current.get("MappingOrder") or 0
            ):
                resolved[key] = row
        return list(resolved.values())

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaId") or "")).first()
        feature = Feature.objects.filter(legacy_id=str(row.get("FeatureId") or "")).first()
        if prop is None or feature is None:
            report.skipped += 1
            return
        # `update_or_create` is the residual-dup safety net — it updates rather
        # than tripping the unique constraint if a pair ever slips past the
        # `_remap_deleted_features` dedupe. A legacy link is a manual link:
        # `is_derived=False` even when a GAP-067 derived row got there first.
        through = Property.features.through
        _, created = through.objects.update_or_create(
            property_id=prop.pk,
            feature_id=feature.pk,
            defaults={"sort_order": int(row.get("MappingOrder") or 0), "is_derived": False},
        )
        if created:
            report.created += 1
        else:
            report.updated += 1
