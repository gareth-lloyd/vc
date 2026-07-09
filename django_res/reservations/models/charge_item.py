"""BookingChargeItem — a manual charge/credit line on a booking.

Direct analogue of legacy `VillaBookingDetail` (Price + Notes + CurrencyId):
staff-entered money that sits outside the immutable pricing snapshot and
flows into the guest-facing total and the DEPOSIT/BALANCE payment schedule.
Concierge money is deliberately separate (`BookingConciergeItem` settles on
its own CONCIERGE payment track and never enters `total`).
"""

from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel


class BookingChargeItem(AuditedModel):
    """A signed charge line: positive = charge, negative = credit."""

    booking = models.ForeignKey(
        "reservations.Booking",
        on_delete=models.CASCADE,
        related_name="charge_items",
    )
    label = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Must equal `booking.currency` — the service layer defaults and
    # validates it; the column exists for legacy-import parity.
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="+",
    )
    # False = bills the guest as normal but is excluded from the commission
    # split — the amount flows to the owner verbatim (GAP-076).
    commissionable = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(amount=0),
                name="bookingchargeitem_amount_nonzero",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.label} {self.amount}"
