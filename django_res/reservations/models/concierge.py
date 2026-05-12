"""BookingConciergeItem — one row per requested concierge service."""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from core.models.base import AuditedModel
from reservations.enums import ConciergeStatus, ConciergeTier, ConciergeUnit


class BookingConciergeItem(AuditedModel):
    """A concierge line attached to a booking. No upstream catalogue."""

    booking = models.ForeignKey(
        "reservations.Booking",
        on_delete=models.CASCADE,
        related_name="concierge_items",
    )
    tier = models.CharField(
        max_length=16,
        choices=ConciergeTier.choices,
        default=ConciergeTier.QUINTESSENTIAL,
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    quantity = models.PositiveSmallIntegerField(default=1)
    unit = models.CharField(
        max_length=8,
        choices=ConciergeUnit.choices,
        default=ConciergeUnit.STAY,
    )
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="+",
    )
    status = models.CharField(
        max_length=16,
        choices=ConciergeStatus.choices,
        default=ConciergeStatus.REQUESTED,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self) -> str:
        return f"{self.name} x{self.quantity}"

    def line_total(self) -> Decimal:
        return (Decimal(self.unit_price) * Decimal(self.quantity)).quantize(Decimal("0.01"))
