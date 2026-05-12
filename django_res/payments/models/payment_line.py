"""`PaymentLine` — line-item breakdown of a Payment.

Mostly relevant for concierge payments that bundle several items into one
invoice. The deposit/balance/security-deposit tracks rarely produce a
multi-line payment.
"""

from __future__ import annotations

from django.db import models

from core.models.base import TimestampedModel


class PaymentLine(TimestampedModel):
    """One line of a Payment's invoice breakdown."""

    payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.CASCADE,
        related_name="lines",
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.description} {self.amount}"
