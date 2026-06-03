"""OwnerBlockRequest — an owner's request to block their villa's availability.

A pending request must NOT occupy the calendar: a live `BookingHold` is in the
overlap-blocking set the moment it exists, so a *request* can't be modelled as
one. This separate object carries the PENDING → APPROVED/DECLINED/CANCELLED
lifecycle; only on operator approval does `OwnerBlockRequestService` place the
real (indefinite) hold and point `resulting_hold` at it.

Lives in `reservations` (not `owners`) because approval creates a `BookingHold`
— it FKs *down* to properties/accounts, never up. No soft delete: the `status`
enum is the lifecycle.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models.base import TimestampedModel
from reservations.enums import OwnerBlockKind, OwnerBlockRequestStatus


class OwnerBlockRequest(TimestampedModel):
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        related_name="owner_block_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owner_block_requests",
    )
    date_from = models.DateField()
    date_to = models.DateField()
    kind = models.CharField(
        max_length=16,
        choices=OwnerBlockKind.choices,
        default=OwnerBlockKind.OWNER_STAY,
    )
    notes = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=OwnerBlockRequestStatus.choices,
        default=OwnerBlockRequestStatus.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True, default="")
    resulting_hold = models.ForeignKey(
        "reservations.BookingHold",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        indexes = [
            models.Index(fields=["property", "status"]),
            models.Index(fields=["requested_by", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(date_from__lt=models.F("date_to")),
                name="ownerblockrequest_date_from_lt_date_to",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Block request #{self.pk} on property {self.property_id} ({self.status})"
