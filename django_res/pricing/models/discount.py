"""Discount rules — promo codes and property-level auto-applied discounts."""

from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel
from pricing.enums import DiscountKind, RuleKind


class Discount(AuditedModel):
    """A discount rule attached to a property (GAP-056: the card scope is gone)."""

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="discounts",
    )
    name = models.CharField(max_length=128)
    code = models.CharField(max_length=64, unique=True, null=True, blank=True)
    rule_kind = models.CharField(max_length=16, choices=RuleKind.choices)
    kind = models.CharField(max_length=8, choices=DiscountKind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    min_nights = models.PositiveSmallIntegerField(default=0)
    threshold_days = models.PositiveSmallIntegerField(null=True, blank=True)
    valid_from = models.DateField()
    valid_to = models.DateField()
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["property", "name"]
        indexes = [
            models.Index(fields=["property", "is_active"]),
            models.Index(fields=["code"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.rule_kind})"
