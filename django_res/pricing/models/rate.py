"""RatePlan, RateCard, RatePeriod, RateRule — the rate model (GAP-056 expand)."""

from __future__ import annotations

from typing import Any

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


class RatePeriod(AuditedModel):
    """A disjoint date window on a plan; owns the dates its bands inherit (GAP-056).

    Replaces the flattened ``RateRule.date_from/date_to`` with an honest
    date-axis level: periods on one plan are disjoint (EXCLUDE), and each period
    holds a party-band set (its ``RateRule`` children). Dates are **inclusive**
    (``date_from == date_to`` is a legitimate single-day period). ``min_nights``/
    ``max_nights`` are nullable per-period overrides of the villa default; ``name``
    is an optional operator label with no grouping semantics.
    """

    plan = models.ForeignKey(
        RatePlan,
        on_delete=models.CASCADE,
        related_name="periods",
    )
    name = models.CharField(max_length=128, blank=True, default="")
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
        ]
        indexes = [
            models.Index(fields=["plan", "date_from", "date_to"]),
        ]

    def __str__(self) -> str:
        return f"{self.plan_id} [{self.date_from}..{self.date_to}]"


class RateRule(AuditedModel):
    """The fundamental price row: a date sub-range x party-size band on a card."""

    card = models.ForeignKey(
        RateCard,
        on_delete=models.CASCADE,
        related_name="rules",
    )
    period = models.ForeignKey(
        RatePeriod,
        on_delete=models.CASCADE,
        related_name="rules",
        null=True,
        blank=True,
        help_text=(
            "GAP-056 date-axis parent. Nullable transitionally while `card`/dates "
            "still exist; populated by the `save()` shim on every write and made "
            "non-null when `RateCard` is dropped."
        ),
    )
    date_from = models.DateField()
    date_to = models.DateField()
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
        ordering = ["card", "date_from"]
        constraints = [
            models.CheckConstraint(
                # GAP-056: inclusive dates — single-day rules (date_from == date_to)
                # are valid so ragged segmentation can persist single-day fragments.
                condition=models.Q(date_from__lte=models.F("date_to")),
                name="raterule_date_from_lte_date_to",
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
        ]

    def __str__(self) -> str:
        return (
            f"{self.card_id} [{self.date_from}..{self.date_to}] {self.min_party}-{self.max_party}"
        )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Transitional GAP-056 shim: derive `period` from the card + dates.

        Every write path — the view/serializer, `RateRuleFactory`, and the ~60
        direct `RateRule.objects.create(card=…, date_from=…)` sites — goes
        through `save()`, so populating the new FK here keeps the whole suite
        green while `period` is still nullable. When `period` is already set
        (native creates, backfilled rows, updates) this is a no-op. A span that
        does not match an existing period's exact dates forces a new period,
        which the periods-disjoint EXCLUDE rejects if it overlaps — the honest
        grid enforcing itself. Removed in Unit 9 when `RateCard` is dropped.
        """
        if self.period_id is None and self.card_id is not None:
            # No `is_active` in defaults: sibling bands (and, transitionally,
            # rules from a second overlapping card) share one period by `(plan,
            # dates)`, so seeding it from *this* card's is_active would make the
            # shared period's flag order-dependent. Period activeness is
            # period-level — defaults to the model's True, managed in Unit 6.
            period, _ = RatePeriod.objects.get_or_create(
                plan=self.card.plan,
                date_from=self.date_from,
                date_to=self.date_to,
            )
            self.period = period
        super().save(*args, **kwargs)
