"""DamageClaim — a structured claim against a booking's security deposit.

The claim is the *why* behind a `SecurityDeposit` capture / partial refund:
`payments.SecurityDeposit.damage_claim` points here (SET_NULL) so a capture is
always justified by a referenceable record (BUG-008). The model carries the
spec's full shape (`product-design/01-domain-model.md`: description, amount,
itemized lines, photos, guest acceptance) but the surrounding workflow — the
operator report sub-form, photo uploads, threshold permissions, the damages
email, and the enforced approval state machine — lands with workflow 8/17.
`itemized_lines` / `photos` are JSON scaffolds until that upload pipeline ships.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from core.models.base import AuditedModel
from core.refs import reference_db_default
from reservations.enums import DamageClaimStatus


class DamageClaim(AuditedModel):
    """A damages claim raised against a booking, justifying an SD capture."""

    reference = models.CharField(
        max_length=32,
        unique=True,
        db_default=reference_db_default("DC", sequence="damage_claim_reference_seq"),
    )
    booking = models.ForeignKey(
        "reservations.Booking",
        on_delete=models.PROTECT,
        related_name="damage_claims",
    )
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="+",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField()
    status = models.CharField(
        max_length=16,
        choices=DamageClaimStatus.choices,
        default=DamageClaimStatus.OPEN.value,
    )
    # Scaffolds for the workflow-8 damages report; the upload/itemisation UI
    # that populates them ships with that feature.
    itemized_lines = models.JSONField(default=list, blank=True)
    photos = models.JSONField(default=list, blank=True)
    accepted_by_guest_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["booking", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="damage_claim_amount_positive",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.reference
