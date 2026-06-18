"""BookingGuest — through-model attaching Guests to a Booking by role.

A booking always has exactly one LEAD guest (mirrored on `Booking.guest`
for read convenience), zero-or-more CO_TRAVELLER rows, at most one PAYER,
and zero-or-more CC_ONLY recipients used by the comms layer for template
addressee resolution.

The LEAD row is the source of truth; `Booking.guest` is a denormalised
pointer kept in sync by a `post_save` signal (`_booking_guest_post_save`
in `reservations.signals`) so existing booking-list reads against
`booking.guest_id` keep working without a refactor.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from core.fields import CIEmailField
from core.models.base import AuditedModel
from reservations.enums import BookingGuestRole


class BookingGuest(AuditedModel):
    """Through-row attaching a Guest to a Booking under one role."""

    booking = models.ForeignKey(
        "reservations.Booking",
        on_delete=models.CASCADE,
        related_name="booking_guests",
    )
    guest = models.ForeignKey(
        "reservations.Guest",
        on_delete=models.PROTECT,
        related_name="booking_guests",
    )
    # GAP-045 Unit 3a: parallel customer FK to the unified Person. Nullable
    # during the expand/contract transition; reads/writes cut over in Unit 3c.
    person = models.ForeignKey(
        "accounts.Person",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="booking_guests",
    )
    role = models.CharField(
        max_length=16,
        choices=BookingGuestRole.choices,
    )
    email_override = CIEmailField(blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "guest", "role"],
                name="bookingguest_unique_booking_guest_role",
            ),
            models.UniqueConstraint(
                fields=["booking"],
                condition=Q(role=BookingGuestRole.LEAD.value),
                name="bookingguest_one_lead_per_booking",
            ),
            models.UniqueConstraint(
                fields=["booking"],
                condition=Q(role=BookingGuestRole.PAYER.value),
                name="bookingguest_one_payer_per_booking",
            ),
        ]
        indexes = [
            models.Index(fields=["booking", "role"]),
            models.Index(fields=["guest", "role"]),
        ]
        ordering = ["booking_id", "role", "id"]

    def __str__(self) -> str:
        return f"BookingGuest #{self.pk} ({self.role})"


__all__ = ["BookingGuest"]
