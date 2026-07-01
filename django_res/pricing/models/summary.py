"""Signal-rebuilt cache: per-(property, currency) min/max rate display."""

from __future__ import annotations

from django.db import models

from core.models.base import TimestampedModel


class VillaPricingSummary(TimestampedModel):
    """Denormalised website min/max display cache.

    Rebuilt by `pricing.tasks.rebuild_summary` on every RateBand/RatePlan
    change. Never written by views/admin.
    """

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="pricing_summaries",
    )
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="pricing_summaries",
    )
    min_nightly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_nightly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    min_weekly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_weekly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    next_available_date = models.DateField(null=True, blank=True)
    min_party = models.PositiveSmallIntegerField(default=1)
    max_party = models.PositiveSmallIntegerField(default=1)
    rebuilt_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["property", "currency"],
                name="pricingsummary_unique_property_currency",
            ),
        ]
        verbose_name = "villa pricing summary"
        verbose_name_plural = "villa pricing summaries"

    def __str__(self) -> str:
        return f"summary({self.property_id}, {self.currency_id})"
