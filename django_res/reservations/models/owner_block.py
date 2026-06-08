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
from reservations.enums import OwnerBlockKind, OwnerBlockSource, OwnerBlockStatus


class OwnerBlock(TimestampedModel):
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        related_name="owner_block_requests",
    )
    # NULL for ICAL-imported blocks: an automated feed poll has no human actor
    # (the `actor=None` system-caller sentinel). MANUAL blocks always carry a
    # creator — enforced by the `ownerblock_manual_requires_creator` constraint.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="owner_block_requests",
    )
    source = models.CharField(
        max_length=16,
        choices=OwnerBlockSource.choices,
        default=OwnerBlockSource.MANUAL,
    )
    # Reconciliation key for ICAL blocks — the half-open date range the block
    # represents (`<date_from>_<date_to>`). The poller diffs the feed's coalesced
    # ranges against existing ICAL blocks by this key, so block identity is the
    # merged range, not the (unstable) iCal UID. Blank for MANUAL blocks.
    idempotency_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
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
    # Contest is a flag orthogonal to the lifecycle: staff can dispute the
    # dates, which notifies the owner but keeps the block APPROVED (the hold
    # stays). A null `contested_at` means "not contested".
    contested_at = models.DateTimeField(null=True, blank=True)
    contested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    contest_reason = models.TextField(blank=True, default="")

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
            # A manual block must record who made it; only ICAL imports may have
            # a null creator.
            models.CheckConstraint(
                condition=Q(source=OwnerBlockSource.ICAL.value) | Q(created_by__isnull=False),
                name="ownerblock_manual_requires_creator",
            ),
            # One live ICAL block per (property, range). Belt-and-braces behind
            # the poller's reconcile diff; scoped to APPROVED so a cancelled
            # block doesn't prevent re-importing the same range later.
            models.UniqueConstraint(
                fields=["property", "idempotency_key"],
                condition=Q(status=OwnerBlockStatus.APPROVED.value) & ~Q(idempotency_key=""),
                name="unique_active_ical_block_per_property_key",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Owner block #{self.pk} on property {self.property_id} ({self.status})"
