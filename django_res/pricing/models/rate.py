"""RatePlan, RatePeriod, RateBand — the rate model (GAP-056 contract).

`Property → RatePlan → RatePeriod (date axis, disjoint per plan) → RateBand
(party band, disjoint per period)`. Every `(night, party)` resolves to exactly
one cell. The old `RateCard` precedence level is gone (no prod villa used it).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone

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
    prices_by_occupancy = models.BooleanField(
        default=False,
        help_text=(
            "False = one flat price per period (party size ignored); "
            "True = per-party-size RateBands."
        ),
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

    @property
    def is_historical(self) -> bool:
        """True once the whole date window has elapsed (``date_to`` before today).

        Historical periods are read-only in the workbench: their dates, name, and
        bands (including inline price edits) are locked, and the period/its bands
        cannot be deleted. Enforced in the serializers/views; the frontend mirrors
        the lock by disabling the row's controls.
        """
        return self.date_to < timezone.localdate()


class RateBand(AuditedModel):
    """The fundamental price row: a party-size band on a period (inherits its dates).

    ``nightly``/``weekly`` are the **base** prices — what carry-over, projection
    and next-year copies read. A mid-season cut is recorded *alongside* the base
    (Q-018): either ``reduction_percent`` (applies to both prices) or explicit
    ``reduced_nightly``/``reduced_weekly`` new amounts, never both. Quoting reads
    the derived ``effective_nightly``/``effective_weekly``; nothing effective is
    stored, so a discounted year can never leak into the next.
    """

    period = models.ForeignKey(
        RatePeriod,
        on_delete=models.CASCADE,
        related_name="bands",
    )
    min_party = models.PositiveSmallIntegerField(default=1)
    max_party = models.PositiveSmallIntegerField()
    nightly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    weekly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reduction_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    reduced_nightly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reduced_weekly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reduced_at = models.DateField(null=True, blank=True)
    reduction_reason = models.CharField(max_length=200, blank=True)
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
            # Q-018 reduction legality. NULL rows pass via explicit __isnull
            # predicates, never three-valued-logic accident.
            models.CheckConstraint(
                condition=(
                    models.Q(reduction_percent__isnull=True)
                    | (models.Q(reduction_percent__gt=0) & models.Q(reduction_percent__lt=100))
                ),
                name="rateband_reduction_percent_range",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(reduction_percent__isnull=True)
                    | (
                        models.Q(reduced_nightly__isnull=True)
                        & models.Q(reduced_weekly__isnull=True)
                    )
                ),
                name="rateband_reduction_percent_excludes_fixed",
            ),
            # Fixed amounts are strictly 0 < reduced < base: zero/negative would
            # smuggle in the free stay the percent range (<100) forbids.
            models.CheckConstraint(
                condition=(
                    models.Q(reduced_nightly__isnull=True)
                    | (
                        models.Q(nightly__isnull=False)
                        & models.Q(reduced_nightly__gt=0)
                        & models.Q(reduced_nightly__lt=models.F("nightly"))
                    )
                ),
                name="rateband_reduced_nightly_lt_base",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(reduced_weekly__isnull=True)
                    | (
                        models.Q(weekly__isnull=False)
                        & models.Q(reduced_weekly__gt=0)
                        & models.Q(reduced_weekly__lt=models.F("weekly"))
                    )
                ),
                name="rateband_reduced_weekly_lt_base",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_poa=False)
                    | (
                        models.Q(reduction_percent__isnull=True)
                        & models.Q(reduced_nightly__isnull=True)
                        & models.Q(reduced_weekly__isnull=True)
                    )
                ),
                name="rateband_poa_excludes_reduction",
            ),
        ]
        indexes = [
            models.Index(fields=["period", "min_party"]),
        ]

    def __str__(self) -> str:
        return f"{self.period_id} {self.min_party}-{self.max_party}"

    @property
    def has_reduction(self) -> bool:
        return (
            self.reduction_percent is not None
            or self.reduced_nightly is not None
            or self.reduced_weekly is not None
        )

    def _effective(self, base: Decimal | None, fixed: Decimal | None) -> Decimal | None:
        """Derive one effective price: fixed amount wins, else percent off base.

        Quantized to 0.01 with the engine's rounding (ROUND_HALF_EVEN, the
        Decimal default) so a quoted price never differs from a displayed one.
        A NULL base stays NULL — a reduction never invents a price.
        """
        if base is None:
            return None
        if fixed is not None:
            return fixed
        if self.reduction_percent is not None:
            factor = (Decimal("100") - self.reduction_percent) / Decimal("100")
            return (base * factor).quantize(Decimal("0.01"))
        return base

    @property
    def effective_nightly(self) -> Decimal | None:
        return self._effective(self.nightly, self.reduced_nightly)

    @property
    def effective_weekly(self) -> Decimal | None:
        return self._effective(self.weekly, self.reduced_weekly)
