from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel, TimestampedModel
from properties.enums import RoomPlacement


class Room(AuditedModel):
    """A bedroom (or sleeping area) within a `Property`."""

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="rooms",
    )
    name = models.CharField(max_length=128)
    placement = models.CharField(
        max_length=16,
        choices=RoomPlacement.choices,
        default=RoomPlacement.MAIN_HOUSE,
    )
    website_description = models.TextField(blank=True)
    vc_notes = models.TextField(blank=True)
    is_ensuite = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["property_id", "sort_order", "name"]

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
