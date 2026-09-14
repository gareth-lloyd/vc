"""RatePlan, RatePeriod, RateBand — the rate model (GAP-056 contract).

`Property → RatePlan → RatePeriod (date axis, disjoint per plan) → RateBand
(party band, disjoint per period)`. Every `(night, party)` resolves to exactly
one cell. The old `RateCard` precedence level is gone (no prod villa used it).
"""

from __future__ import annotations

import builtins
from decimal import Decimal
from typing import Any

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeBoundary, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.fields import DateRangeFunc, Int4RangeFunc
from core.models.base import AuditedModel
from properties.enums import PriceBasis

# Shared by the model's `clean()` (admin/forms) and `RatePlanSerializer` (API).
REGIME_LOCKED_MESSAGE = (
    "Property and currency are fixed once a plan has periods; create a new plan instead."
)


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
    # Retry dedupe for the removed `:duplicate` (SMELL-009; GAP-110 dropped
    # the feature). Orphaned — nothing writes it; dropped with the envelope in
    # the GAP-110 contract migration.
    idempotency_key = models.CharField(max_length=64, blank=True, default="", db_index=True)

    class Meta:
        ordering = ["property", "-effective_from"]
        constraints = [
            # FG-010 backstop for the removed `duplicate_rate_plan` pre-check;
            # orphaned with the field above, dropped in the contract migration.
            models.UniqueConstraint(
                fields=["property", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="rateplan_idempotency_key_unique_per_property",
            ),
        ]
        indexes = [
            models.Index(fields=["property", "currency", "is_active"]),
            models.Index(fields=["effective_from", "effective_to"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.currency_id})"

    # GAP-110: periods carry stamped copies of the plan's (property, currency)
    # — the regime partition key — so neither may move once a period exists.
    # Both checks compare against what the periods actually carry (one query
    # each), which also catches stamp drift from any raw write.
    def property_locked_against(self, property_id: int) -> bool:
        return self.pk is not None and self.periods.exclude(property_id=property_id).exists()

    def currency_locked_against(self, currency_id: int) -> bool:
        return self.pk is not None and self.periods.exclude(currency_id=currency_id).exists()

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.property_locked_against(self.property_id):
            errors["property"] = REGIME_LOCKED_MESSAGE
        if self.currency_locked_against(self.currency_id):
            errors["currency"] = REGIME_LOCKED_MESSAGE
        if errors:
            raise ValidationError(errors)


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
    # GAP-110: denormalised copies of the plan's regime key. Postgres EXCLUDE
    # can't join through `plan`, so the regime-wide no-overlap partition needs
    # them on the row. Derived — `save()` stamps them from the plan and ignores
    # caller input; not audit-tracked (`pricing/0008` expand, `0009` contract).
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        related_name="rate_periods",
        editable=False,
    )
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="rate_periods",
        editable=False,
    )
    name = models.CharField(max_length=128)
    date_from = models.DateField()
    date_to = models.DateField()
    min_nights = models.PositiveSmallIntegerField(null=True, blank=True)
    max_nights = models.PositiveSmallIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Re-derive the stamps whenever `plan_id` is being written, so they
        # only ever land together with it. A partial save that leaves `plan`
        # alone leaves them alone too (and `update_fields=[]` stays a no-op).
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "plan" in update_fields:
            self.property_id = self.plan.property_id
            self.currency_id = self.plan.currency_id
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "property", "currency"}
        super().save(*args, **kwargs)

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
            # Inclusive '[]' bounds: date_to is the last priced day, so
            # adjacent periods must not share a boundary date. The pricing
            # engine iterates half-open [from, to) *nights* and checks each
            # against inclusive period dates (pricing/services/engine.py) —
            # the two conventions meet only there; don't change one without
            # the other.
            #
            # GAP-110: partitioned on the stamped regime key, not the plan —
            # at most one plan prices a night in a currency for a property.
            # Ungated by `is_active` (period or plan): an inactive regime still
            # owns its dates; hand them over by deleting its periods.
            ExclusionConstraint(
                name="rateperiod_no_overlap",
                expressions=[
                    ("property", RangeOperators.EQUAL),
                    ("currency", RangeOperators.EQUAL),
                    (
                        DateRangeFunc(
                            "date_from",
                            "date_to",
                            RangeBoundary(inclusive_lower=True, inclusive_upper=True),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
            ),
        ]
        indexes = [
            models.Index(fields=["plan", "date_from", "date_to"]),
            # Regime lookups (GAP-110): the engine selects periods by
            # (property, currency) over a stay window, plan inferred after.
            models.Index(fields=["property", "currency", "date_from", "date_to"]),
        ]

    def __str__(self) -> str:
        return f"{self.plan_id} [{self.date_from}..{self.date_to}]"

    # `builtins.property`: the `property` FK shadows the decorator in the
    # class body (same dance as `reservations.Booking`).
    @builtins.property
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
            # Inclusive '[]' party bounds: min_party..max_party are both
            # bookable sizes, so bands on one period must not share a size.
            ExclusionConstraint(
                name="rateband_bands_no_overlap",
                expressions=[
                    ("period", RangeOperators.EQUAL),
                    (
                        Int4RangeFunc(
                            "min_party",
                            "max_party",
                            RangeBoundary(inclusive_lower=True, inclusive_upper=True),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
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
