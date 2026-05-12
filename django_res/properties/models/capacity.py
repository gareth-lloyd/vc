from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel


class PropertyCapacity(AuditedModel):
    """Headcount and room-count facts for a `Property`."""

    property = models.OneToOneField(
        "properties.Property",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="capacity",
    )
    guests = models.PositiveSmallIntegerField(default=0)
    additional_guests = models.PositiveSmallIntegerField(default=0)
    bedrooms = models.PositiveSmallIntegerField(default=0)
    ensuites = models.PositiveSmallIntegerField(default=0)
    bathrooms = models.PositiveSmallIntegerField(default=0)
    size_sqm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return f"Capacity for property #{self.property_id}"
