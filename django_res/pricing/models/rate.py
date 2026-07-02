"""RatePlan, RatePeriod, RateBand — the rate model (GAP-056 contract).

`Property → RatePlan → RatePeriod (date axis, disjoint per plan) → RateBand
(party band, disjoint per period)`. Every `(night, party)` resolves to exactly
one cell. The old `RateCard` precedence level is gone (no prod villa used it).
"""

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
            "Opt-in nightly rate used when no RateBand covers a night. "
            "NULL = no fallback (uncovered nights raise NoRateAvailable)."
        ),
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["property", "-effective_from"]
        indexes = [
            models.Index(fields=["property", "currency", "is_active"]),
            models.Index(fields=["effective_from", "effective_to"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.currency_id})"


class RatePeriod(AuditedModel):
    """A disjoint date window on a plan; owns the dates its bands inherit (GAP-056).

    Replaces the flattened ``RateBand.date_from/date_to`` with an honest
    date-axis level: periods on one plan are disjoint (EXCLUDE), and each period
    holds a party-band set (its ``RateBand`` children). Dates are **inclusive**
    (``date_from == date_to`` is a legitimate single-day period). ``min_nights``/
    ``max_nights`` are nullable per-period overrides of the villa default; ``name``
    is a compulsory operator label (GAP-059, CHECK-enforced) with no grouping
    semantics — season *tiers* are a separate concern (Q-022). Writers with no
    meaningful label derive the date-span placeholder
    (`pricing.services.period_names.derive_period_name`).
    """

    plan = models.ForeignKey(
        RatePlan,
        on_delete=models.CASCADE,
        related_name="periods",
    )
    name = models.CharField(max_length=128)
    date_from = models.DateField()
    date_to = models.DateField()
    min_nights = models.PositiveSmallIntegerField(null=True, blank=True)
    max_nights = models.PositiveSmallIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["plan", "date_from"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_from__lte=models.F("date_to")),
                name="rateperiod_date_from_lte_date_to",
            ),
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="rateperiod_name_not_blank",
            ),
        ]
        indexes = [
            models.Index(fields=["plan", "date_from", "date_to"]),
        ]

    def __str__(self) -> str:
        return f"{self.plan_id} [{self.date_from}..{self.date_to}]"


class RateBand(AuditedModel):
    """The fundamental price row: a party-size band on a period (inherits its dates)."""

    period = models.ForeignKey(
        RatePeriod,
        on_delete=models.CASCADE,
        related_name="bands",
    )
    min_party = models.PositiveSmallIntegerField(default=1)
    max_party = models.PositiveSmallIntegerField()
    nightly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    weekly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_poa = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["period", "min_party"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(min_party__lte=models.F("max_party")),
                name="rateband_min_party_lte_max_party",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(nightly__isnull=False)
                    | models.Q(weekly__isnull=False)
                    | models.Q(is_poa=True)
                ),
                name="rateband_has_price_or_poa",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_poa=False)
                    | (models.Q(nightly__isnull=True) & models.Q(weekly__isnull=True))
                ),
                name="rateband_poa_excludes_price",
            ),
        ]
        indexes = [
            models.Index(fields=["period", "min_party"]),
        ]

    def __str__(self) -> str:
        return f"{self.period_id} {self.min_party}-{self.max_party}"
