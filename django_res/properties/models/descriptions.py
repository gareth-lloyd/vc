from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel
from properties.enums import DescriptionSection


class PropertyDescription(AuditedModel):
    """A rich-text description block for one section of a `Property`."""

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="descriptions",
    )
    section = models.CharField(
        max_length=16,
        choices=DescriptionSection.choices,
    )
    body = models.TextField(blank=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["property", "section"],
                name="one_description_per_section",
            ),
        ]
        ordering = ["property_id", "section"]

    def __str__(self) -> str:
        return f"{self.section} description for property #{self.property_id}"
