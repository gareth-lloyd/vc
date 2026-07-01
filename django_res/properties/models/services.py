"""Property-scoped catalogue of included, date-ranged services (chef, housekeeping…).

A `PropertyService` is the first-class home for "what's included" in the rate —
promoted out of the free-text `RatePlan.inclusion` (GAP-037). It is purely
informational: the cost is already baked into the rate, so unlike `Extra` it
never flows into a quote total. Its own absolute date band lets inclusions vary
independently of the rate calendar (a summer-only chef on a flat-rate villa is
one service, not a duplicate season).
"""

from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel


class PropertyService(AuditedModel):
    """An included service the engine surfaces on quotes whose stay overlaps its band."""

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="services",
    )
    name = models.CharField(max_length=128)
    copy = models.TextField()
    """Guest-facing description; seeds the quote "Includes:" line (legacy RatePlan.inclusion)."""
    notes = models.TextField(blank=True)
    """Internal-only remarks, never shown to guests."""
    applies_from = models.DateField(null=True, blank=True)
    applies_to = models.DateField(null=True, blank=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["property", "sort_order", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(applies_from__isnull=True)
                    | models.Q(applies_to__isnull=True)
                    | models.Q(applies_from__lte=models.F("applies_to"))
                ),
                name="propertyservice_applies_from_lte_applies_to",
            ),
        ]
        indexes = [
            models.Index(fields=["property", "is_active", "sort_order"]),
        ]

    def __str__(self) -> str:
        return self.name
