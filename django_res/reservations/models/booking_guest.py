"""BookingGuest — through-model attaching Persons to a Booking by role.

A booking always has exactly one LEAD person (mirrored on `Booking.person`
for read convenience), zero-or-more CO_TRAVELLER rows, at most one PAYER,
and zero-or-more CC_ONLY recipients used by the comms layer for template
addressee resolution.

The LEAD row is the source of truth; `Booking.person` is a denormalised
pointer kept in sync by a `post_save` signal (`_booking_guest_post_save`
in `reservations.signals`) so existing booking-list reads against
`booking.person_id` keep working without a refactor.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from core.fields import CIEmailField
from core.models.base import AuditedModel
from reservations.enums import BookingGuestRole


class BookingGuest(AuditedModel):
    """Through-row attaching a Person to a Booking under one role."""

    booking = models.ForeignKey(
        "reservations.Booking",
        on_delete=models.CASCADE,
        related_name="booking_guests",
    )
    # GAP-045: `person` is the authoritative customer FK.
    person = models.ForeignKey(
        "accounts.Person",
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
                fields=["booking", "person", "role"],
                name="bookingguest_unique_booking_person_role",
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
            models.Index(fields=["person", "role"]),
        ]
        ordering = ["booking_id", "role", "id"]

    def __str__(self) -> str:
        return f"BookingGuest #{self.pk} ({self.role})"


__all__ = ["BookingGuest"]
