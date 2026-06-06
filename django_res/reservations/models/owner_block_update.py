"""OwnerBlockUpdate — append-only feed row, one per owner-block change event.

Mirrors `BookingEvent`: a curated, append-only record the staff "owner blocks"
feed reads, distinct from the `AuditLog` diff trail. It carries the per-user
*seen* state (`OwnerBlockUpdateSeen`) the awareness feed needs — staff move from
gatekeeper to aware observer, so the point of this table is "what changed, and
have I seen it" rather than the field-level audit diff.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models.base import TimestampedModel
from reservations.enums import OwnerBlockUpdateKind


class OwnerBlockUpdate(TimestampedModel):
    block = models.ForeignKey(
        "reservations.OwnerBlock",
        on_delete=models.PROTECT,
        related_name="updates",
    )
    kind = models.CharField(max_length=16, choices=OwnerBlockUpdateKind.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        indexes = [
            models.Index(fields=["block", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"OwnerBlockUpdate #{self.pk} ({self.kind}) on block {self.block_id}"
