"""Property-scoped catalogue of named charges (cleaning, pet fee, heating…)."""

from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel
from pricing.enums import ExtraCalc, ExtraKind


class Extra(AuditedModel):
    """A property-level extra charge that the pricing engine applies at quote time."""

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="extras",
    )
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=16, choices=ExtraKind.choices)
    calc = models.CharField(max_length=32, choices=ExtraCalc.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="extras",
    )
    is_mandatory = models.BooleanField(default=True)
    # False = stays in the guest total but is excluded from the commission and
    # tax bases; the amount passes through to the owner verbatim (GAP-076).
    # Per-villa taxability policy for these extras is deferred to GAP-079.
    commissionable = models.BooleanField(default=True)
    applies_from = models.DateField(null=True, blank=True)
    applies_to = models.DateField(null=True, blank=True)
    min_party = models.PositiveSmallIntegerField(null=True, blank=True)
    max_party = models.PositiveSmallIntegerField(null=True, blank=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    # Retry dedupe for `:duplicate` (SMELL-009). Blank = "no idempotency
    # requested" — only client-supplied keys enter the partial unique below.
    idempotency_key = models.CharField(max_length=64, blank=True, default="", db_index=True)

    class Meta:
        ordering = ["property", "sort_order", "name"]
        constraints = [
            # FG-010 backstop for `duplicate_extra`'s check-then-create
            # pre-check. Scoped to the DESTINATION property (where the clone
            # lands), matching the scope the service queries.
            models.UniqueConstraint(
                fields=["property", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="extra_idempotency_key_unique_per_property",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(applies_from__isnull=True)
                    | models.Q(applies_to__isnull=True)
                    | models.Q(applies_from__lte=models.F("applies_to"))
                ),
                name="extra_applies_from_lte_applies_to",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(min_party__isnull=True)
                    | models.Q(max_party__isnull=True)
                    | models.Q(min_party__lte=models.F("max_party"))
                ),
                name="extra_min_party_lte_max_party",
            ),
        ]
        indexes = [
            models.Index(fields=["property", "is_active", "sort_order"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.kind})"
