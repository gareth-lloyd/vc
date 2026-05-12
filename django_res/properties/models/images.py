from __future__ import annotations

from django.db import models
from django.db.models import Q

from core.models.base import AuditedModel
from properties.enums import ImageKind


class PropertyImage(AuditedModel):
    """An image attached to a `Property`."""

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="properties/%Y/%m/")
    kind = models.CharField(
        max_length=16,
        choices=ImageKind.choices,
        default=ImageKind.GALLERY,
    )
    name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["property"],
                condition=Q(kind=ImageKind.HERO, is_active=True),
                name="unique_active_hero_per_property",
            ),
        ]
        ordering = ["property_id", "sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.kind} image #{self.pk} for property #{self.property_id}"
