"""Global property-creation defaults singleton (GAP-070).

Backs `GET/PATCH /api/v1/property-defaults`. One row keyed by `pk=1`
(`PropertyDefaults.get_solo()` creates it on first access — same pattern as
`core.SystemSettings`). Snapshotted into concrete `PropertySettings` /
`PropertyFinance` values when a property is created; changing a default never
touches existing properties.

Deliberately excludes per-owner finance data (contact, bank_*, tax_number) —
a global default bank account stamped onto every new villa would be wrong.
Field defaults ARE the seeded starter set (GAP-068 confirmed values), so the
seed migration and a fresh `get_solo()` agree.
"""

from __future__ import annotations

from datetime import time
from typing import Any

from django.db import models

from core.models.base import AuditedModel
from properties.enums import (
    AvailabilityDefault,
    CommissionCalcType,
    DepositCalcType,
    PrefilledChangeOverDay,
    PriceBasis,
    SecurityDepositCalcType,
    SecurityDepositPaymentMethod,
)


class PropertyDefaults(AuditedModel):
    """Singleton row: the starter values every new property is created with."""

    # --- settings-side defaults (mirrors the old GroupSettings columns) ---
    availability_default = models.CharField(
        max_length=16,
        choices=AvailabilityDefault.choices,
        default=AvailabilityDefault.AVAILABLE,
    )
    bookings_require_pre_approval = models.BooleanField(default=False)
    requires_enquiry_first = models.BooleanField(default=False)
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    check_in_time = models.TimeField(null=True, blank=True, default=time(16, 30))
    check_out_time = models.TimeField(null=True, blank=True, default=time(10, 30))
    changeover_day = models.CharField(
        max_length=8,
        choices=PrefilledChangeOverDay.choices,
        default=PrefilledChangeOverDay.ANY,
    )
    min_nights_rental = models.PositiveSmallIntegerField(default=1)
    min_nights_rental_note = models.TextField(blank=True)
    # NOT a pricing authority (GAP-035/SMELL-021) — seeds the PropertySettings
    # pre-fill at property creation; the engine prices from RatePlan.price_basis.
    prices_entered_as = models.CharField(
        max_length=8,
        choices=PriceBasis.choices,
        default=PriceBasis.GROSS,
        help_text="Entry-form pre-fill for new rate plans; "
        "the engine prices from RatePlan.price_basis.",
    )
    hold_duration_hours = models.PositiveSmallIntegerField(default=48)

    # --- finance-policy defaults (mirrors the old GroupFinance columns,
    # minus per-owner contact/bank/tax-number data) ---
    commission_calculation_type = models.CharField(
        max_length=8,
        choices=CommissionCalcType.choices,
        default=CommissionCalcType.PERCENT,
    )
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_note = models.TextField(blank=True)

    tax_is_exempt = models.BooleanField(default=False)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    deposit_required = models.BooleanField(default=True)
    deposit_calculation_type = models.CharField(
        max_length=8,
        choices=DepositCalcType.choices,
        default=DepositCalcType.PERCENT,
    )
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=30)
    interim_required = models.BooleanField(default=False)
    interim_calculation_type = models.CharField(
        max_length=8,
        choices=DepositCalcType.choices,
        default=DepositCalcType.PERCENT,
    )
    interim_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    days_interim_due_before_arrival = models.PositiveSmallIntegerField(default=0)
    days_balance_due_before_arrival = models.PositiveSmallIntegerField(default=60)

    security_deposit_required = models.BooleanField(default=True)
    security_deposit_calculation_type = models.CharField(
        max_length=8,
        choices=SecurityDepositCalcType.choices,
        default=SecurityDepositCalcType.FIXED,
    )
    security_deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    security_deposit_days_due_before_arrival = models.PositiveSmallIntegerField(default=14)
    security_deposit_days_refunded_after_departure = models.PositiveSmallIntegerField(default=7)
    security_deposit_payment_method = models.CharField(
        max_length=16,
        choices=SecurityDepositPaymentMethod.choices,
        default=SecurityDepositPaymentMethod.CARD_HOLD,
    )

    cancellation_fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cancellation_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cancellation_window_days = models.PositiveSmallIntegerField(default=0)
    cancellation_notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "property defaults"
        verbose_name_plural = "property defaults"

    def __str__(self) -> str:
        return "Property defaults"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Enforce singleton — always pk=1."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> PropertyDefaults:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
