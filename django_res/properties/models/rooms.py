from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel, TimestampedModel
from properties.enums import BedSize, EnsuiteType, RoomAccess, RoomFloor, RoomPlacement


class Room(AuditedModel):
    """A bedroom (or sleeping area) within a `Property`."""

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="rooms",
    )
    name = models.CharField(max_length=128)
    # Location axes (GAP-065): "" = unknown for both. `placement` is the
    # building, `floor` the ladder rung — orthogonal, either may be blank.
    placement = models.CharField(
        max_length=16,
        choices=RoomPlacement.choices,
        blank=True,
        default="",
    )
    floor = models.CharField(
        max_length=16,
        choices=RoomFloor.choices,
        blank=True,
        default="",
    )
    # Raw legacy `VillaRoomsPlacement.Name` — the no-loss guarantee: even when
    # parsing can't split it, the exact string survives, human-recoverable.
    placement_note = models.CharField(max_length=255, blank=True, default="")
    website_description = models.TextField(blank=True)
    vc_notes = models.TextField(blank=True)
    is_ensuite = models.BooleanField(default=False)
    # Facet columns (GAP-064): "" = unknown. `ensuite_type` refines `is_ensuite`
    # when known; a blank type never implies "not ensuite".
    ensuite_type = models.CharField(
        max_length=16,
        choices=EnsuiteType.choices,
        blank=True,
        default="",
    )
    access = models.CharField(
        max_length=16,
        choices=RoomAccess.choices,
        blank=True,
        default="",
    )
    sort_order = models.PositiveIntegerField(default=0)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["property_id", "sort_order", "name"]
        constraints = [
            # A typed ensuite must also be flagged ensuite; loaders and admin
            # bypass the serializer, so the coherence lives in the DB.
            models.CheckConstraint(
                condition=models.Q(ensuite_type="") | models.Q(is_ensuite=True),
                name="room_ensuite_type_implies_is_ensuite",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.property_id})"


class RoomBeds(TimestampedModel):
    """Bed counts for a `Room`. One row per room."""

    room = models.OneToOneField(
        Room,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="beds",
    )
    double = models.PositiveSmallIntegerField(default=0)
    # Size of the double bed(s) (GAP-066): "" = unspecified. Only meaningful when
    # `double > 0` — the form hides it otherwise (progressive disclosure); the
    # field itself is a plain optional facet with no DB-level gate on `double`.
    double_size = models.CharField(
        max_length=16,
        choices=BedSize.choices,
        blank=True,
        default="",
    )
    twin_double = models.PositiveSmallIntegerField(default=0)
    twin = models.PositiveSmallIntegerField(default=0)
    single = models.PositiveSmallIntegerField(default=0)
    bunk = models.PositiveSmallIntegerField(default=0)
    sofa = models.PositiveSmallIntegerField(default=0)
    childrens = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name_plural = "room beds"

    def __str__(self) -> str:
        return f"Beds for room #{self.room_id}"


class RoomAttribute(TimestampedModel):
    """Admin-curated catalog of per-room amenity tags (GAP-064).

    Deliberately SEPARATE from the property `Feature` taxonomy — room
    amenities carry no category/service_type/pricing coupling. A new
    amenity is a data row a curator adds; no migration, serializer,
    schema or frontend change.
    """

    name = models.CharField(max_length=64)
    # Stable machine key — code, backfill and tests key on `slug`, so
    # relabelling `name` never breaks them.
    slug = models.SlugField(max_length=64, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=64, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    # Retire via deactivate; rows in use can never be hard-deleted (PROTECT).
    is_active = models.BooleanField(default=True)
    # GAP-067 bridge, data-driven: any room carrying this attribute derives
    # this property-level Feature. NULL = a room-only fact (most of them).
    implies_property_feature = models.ForeignKey(
        "properties.Feature",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class RoomAttributeAssignment(models.Model):
    """Through model marking a `Room` as having a `RoomAttribute`.

    Presence semantics: present = yes, absent = not claimed (never
    "confirmed absent").
    """

    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="attribute_links",
    )
    attribute = models.ForeignKey(
        RoomAttribute,
        on_delete=models.PROTECT,
        related_name="+",
    )
    # Per-room nuance, e.g. "sea view from the balcony only".
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "attribute"],
                name="unique_room_attribute",
            ),
        ]
        # Local columns only (the PropertyFeature precedent) — display order by
        # catalog rank is applied by the read path's ordered Prefetch, not here,
        # so plain link reads never drag in a join to the catalog table.
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.attribute_id} on room {self.room_id}"
