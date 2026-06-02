"""RatePlan, RateCard, RateRule — the three-level rate model."""

from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel
from pricing.enums import PriceBasis


class RatePlan(AuditedModel):
    """Groups rate cards for a property under a named season/period."""

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        related_name="rate_plans",
    )
    name = models.CharField(max_length=128)
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="rate_plans",
    )
    price_basis = models.CharField(
        max_length=8,
        choices=PriceBasis.choices,
        default=PriceBasis.GROSS,
    )
    fallback_nightly = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Opt-in nightly rate used when no RateRule covers a night. "
            "NULL = no fallback (uncovered nights raise NoRateAvailable)."
        ),
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    inclusion = models.TextField(blank=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["property", "-effective_from"]
        indexes = [
            models.Index(fields=["property", "currency", "is_active"]),
            models.Index(fields=["effective_from", "effective_to"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.currency_id})"


class RateCard(AuditedModel):
    """Operator-facing rate-card unit. Holds metadata; child rules hold prices."""

    plan = models.ForeignKey(
        RatePlan,
        on_delete=models.CASCADE,
        related_name="cards",
    )
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    min_nights = models.PositiveSmallIntegerField(default=1)
    max_nights = models.PositiveSmallIntegerField(null=True, blank=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["plan", "sort_order", "name"]
        indexes = [
            models.Index(fields=["plan", "sort_order"]),
        ]

    def __str__(self) -> str:
        return self.name


class RateRule(AuditedModel):
    """The fundamental price row: a date sub-range x party-size band on a card."""

    card = models.ForeignKey(
        RateCard,
        on_delete=models.CASCADE,
        related_name="rules",
    )
    date_from = models.DateField()
    date_to = models.DateField()
    min_party = models.PositiveSmallIntegerField(default=1)
    max_party = models.PositiveSmallIntegerField()
    priority = models.PositiveSmallIntegerField(default=0)
    nightly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    weekly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_poa = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["card", "-priority", "date_from"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_from__lt=models.F("date_to")),
                name="raterule_date_from_lt_date_to",
            ),
            models.CheckConstraint(
                condition=models.Q(min_party__lte=models.F("max_party")),
                name="raterule_min_party_lte_max_party",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(nightly__isnull=False)
                    | models.Q(weekly__isnull=False)
                    | models.Q(is_poa=True)
                ),
                name="raterule_has_price_or_poa",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_poa=False)
                    | (models.Q(nightly__isnull=True) & models.Q(weekly__isnull=True))
                ),
                name="raterule_poa_excludes_price",
            ),
        ]
        indexes = [
            models.Index(fields=["card", "date_from", "date_to"]),
            models.Index(fields=["card", "-priority"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.card_id} [{self.date_from}..{self.date_to}] {self.min_party}-{self.max_party}"
        )
