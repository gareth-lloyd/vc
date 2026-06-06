"""OwnerBlock — an owner blocking their own villa's availability.

A block occupies the calendar from creation: `OwnerBlockService.create` places
the real (indefinite) `BookingHold` and points `resulting_hold` at it in the
same transaction, so the block is APPROVED immediately — there is no review
gate. The owner may CANCEL it, which releases the hold.

Lives in `reservations` (not `owners`) because it creates a `BookingHold` — it
FKs *down* to properties/accounts, never up. No soft delete: the `status` enum
is the lifecycle.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models.base import TimestampedModel
from reservations.enums import OwnerBlockKind, OwnerBlockStatus


class OwnerBlock(TimestampedModel):
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        related_name="owner_block_requests",
    )
    created_by = models.ForeignKey(
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
        choices=OwnerBlockStatus.choices,
        default=OwnerBlockStatus.APPROVED,
    )
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
            models.Index(fields=["created_by", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(date_from__lt=models.F("date_to")),
                name="ownerblockrequest_date_from_lt_date_to",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Owner block #{self.pk} on property {self.property_id} ({self.status})"
