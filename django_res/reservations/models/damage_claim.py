"""DamageClaim — a structured claim against a booking's security deposit.

The claim is the *why* behind a `SecurityDeposit` capture / partial refund:
`payments.SecurityDeposit.damage_claim` points here (SET_NULL) so a capture is
always justified by a referenceable record (BUG-008). The model carries the
spec's full shape (`product-design/01-domain-model.md`: description, amount,
itemized lines, photos, guest acceptance). Damages evidence photos live in the
related `DamageClaimPhoto` table (wf8); `itemized_lines` stays a JSON scaffold
until the itemisation UI ships. The remaining workflow bits — threshold
permissions, the damages email, guest acceptance — land later.
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
    # Scaffold for the workflow-8 damages report; the itemisation UI that
    # populates it ships with that feature. Photos are a real relation —
    # `DamageClaimPhoto` below — not a JSON blob.
    itemized_lines = models.JSONField(default=list, blank=True)
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


class DamageClaimPhoto(AuditedModel):
    """A photo evidencing a damages claim (wf8).

    Mirrors `properties.PropertyImage`: a real table with an `ImageField`
    stored via the default storage (filesystem in dev/test, the S3 bucket in
    prod/staging). The image backs a money capture, so create/delete is
    audited (`reservations/apps.py`).
    """

    damage_claim = models.ForeignKey(
        "reservations.DamageClaim",
        on_delete=models.CASCADE,
        related_name="photos",
    )
    image = models.ImageField(upload_to="damage_claims/%Y/%m/")
    caption = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["damage_claim_id", "id"]

    def __str__(self) -> str:
        return f"Photo #{self.pk} for damage claim #{self.damage_claim_id}"
