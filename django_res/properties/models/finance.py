"""Per-property and per-group financial configuration.

`PropertyFinance` is a OneToOne mirror of `Property` with every
operator-editable field nullable; a `NULL` means "inherit from `GroupFinance`".
`GroupFinance` is the floor — every field non-nullable with sensible
defaults. `effective_*()` resolvers merge property → group.

This file mirrors the columns in
`properties/migrations/0002_groupfinance_propertyfinance.py`. It is being
landed by the properties agent; this is a minimal, faithful stub kept in
sync with the migration so cross-app imports (`payments`, `reservations`,
`pricing`) resolve cleanly. Expect the file to be replaced wholesale by
the properties agent's full implementation.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from core.fields import EncryptedTextField
from core.models.base import AuditedModel
from properties.enums import (
    CommissionCalcType,
    DepositCalcType,
    SecurityDepositCalcType,
    SecurityDepositPaymentMethod,
)


class _FinanceFieldMixin:
    """Shared `effective(field)` resolver — looked up by `PropertyFinance`."""

    def effective(self, field: str) -> Any:
        own = getattr(self, field)
        if own is not None and own != "":
            return own
        group_finance = self.property.group.finance  # type: ignore[attr-defined]
        return getattr(group_finance, field)


class PropertyFinance(_FinanceFieldMixin, AuditedModel):
    property = models.OneToOneField(
        "properties.Property",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="finance",
    )
    season = models.ForeignKey(
        "pricing.RatePlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    contact = models.ForeignKey(
        "accounts.Person",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    notes = models.TextField(blank=True)

    commission_calculation_type = models.CharField(
        max_length=8,
        choices=CommissionCalcType.choices,
        null=True,
        blank=True,
    )
    commission_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    commission_note = models.TextField(blank=True)

    tax_number = models.CharField(max_length=64, blank=True)
    tax_is_exempt = models.BooleanField(null=True, blank=True)
    tax_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    bank_account_name = models.CharField(max_length=128, blank=True)
    bank_account_number = EncryptedTextField(blank=True, default="")
    bank_sort_code = EncryptedTextField(blank=True, default="")
    bank_iban = EncryptedTextField(blank=True, default="")
    bank_bic = EncryptedTextField(blank=True, default="")
    bank_name = models.CharField(max_length=128, blank=True)
    bank_address_line_1 = models.CharField(max_length=255, blank=True)
    bank_address_line_2 = models.CharField(max_length=255, blank=True)
    bank_post_code = models.CharField(max_length=32, blank=True)
    bank_city = models.CharField(max_length=128, blank=True)

    deposit_required = models.BooleanField(null=True, blank=True)
    deposit_calculation_type = models.CharField(
        max_length=8,
        choices=DepositCalcType.choices,
        null=True,
        blank=True,
    )
    deposit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    interim_required = models.BooleanField(null=True, blank=True)
    interim_calculation_type = models.CharField(
        max_length=8,
        choices=DepositCalcType.choices,
        null=True,
        blank=True,
    )
    interim_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    days_interim_due_before_arrival = models.PositiveSmallIntegerField(null=True, blank=True)
    days_balance_due_before_arrival = models.PositiveSmallIntegerField(null=True, blank=True)

    security_deposit_required = models.BooleanField(null=True, blank=True)
    security_deposit_calculation_type = models.CharField(
        max_length=8,
        choices=SecurityDepositCalcType.choices,
        null=True,
        blank=True,
    )
    security_deposit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    security_deposit_days_due_before_arrival = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    security_deposit_days_refunded_after_departure = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    security_deposit_payment_method = models.CharField(
        max_length=16,
        choices=SecurityDepositPaymentMethod.choices,
        null=True,
        blank=True,
    )

    cancellation_fee_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    cancellation_fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    cancellation_window_days = models.PositiveSmallIntegerField(null=True, blank=True)
    cancellation_notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"Finance for property #{self.property_id}"

    # ------------------------------------------------------------------
    # Resolvers
    # ------------------------------------------------------------------
    def effective_commission(self) -> dict[str, Any]:
        return {
            "calculation_type": self.effective("commission_calculation_type"),
            "amount": self.effective("commission_amount"),
            "note": self.effective("commission_note"),
        }

    def effective_tax_policy(self) -> dict[str, Any]:
        return {
            "tax_number": self.effective("tax_number"),
            "is_exempt": self.effective("tax_is_exempt"),
            "percentage": self.effective("tax_percentage"),
        }

    def effective_payment_schedule(self) -> dict[str, Any]:
        return {
            "deposit_required": self.effective("deposit_required"),
            "deposit_calculation_type": self.effective("deposit_calculation_type"),
            "deposit_amount": self.effective("deposit_amount"),
            "interim_required": self.effective("interim_required"),
            "interim_calculation_type": self.effective("interim_calculation_type"),
            "interim_amount": self.effective("interim_amount"),
            "days_interim_due_before_arrival": self.effective("days_interim_due_before_arrival"),
            "days_balance_due_before_arrival": self.effective("days_balance_due_before_arrival"),
        }

    def effective_security_deposit_policy(self) -> dict[str, Any]:
        return {
            "required": self.effective("security_deposit_required"),
            "calculation_type": self.effective("security_deposit_calculation_type"),
            "amount": self.effective("security_deposit_amount"),
            "days_due_before_arrival": self.effective(
                "security_deposit_days_due_before_arrival",
            ),
            "days_refunded_after_departure": self.effective(
                "security_deposit_days_refunded_after_departure",
            ),
            "payment_method": self.effective("security_deposit_payment_method"),
        }

    def effective_bank_account(self) -> dict[str, Any]:
        return {
            "account_name": self.effective("bank_account_name"),
            "account_number": self.effective("bank_account_number"),
            "sort_code": self.effective("bank_sort_code"),
            "iban": self.effective("bank_iban"),
            "bic": self.effective("bank_bic"),
            "bank_name": self.effective("bank_name"),
            "address_line_1": self.effective("bank_address_line_1"),
            "address_line_2": self.effective("bank_address_line_2"),
            "post_code": self.effective("bank_post_code"),
            "city": self.effective("bank_city"),
        }

    def effective_cancellation_policy(self) -> dict[str, Any]:
        return {
            "fee_amount": self.effective("cancellation_fee_amount"),
            "fee_percent": self.effective("cancellation_fee_percent"),
            "window_days": self.effective("cancellation_window_days"),
            "notes": self.effective("cancellation_notes"),
        }


class GroupFinance(AuditedModel):
    group = models.OneToOneField(
        "properties.PropertyGroup",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="finance",
    )
    contact = models.ForeignKey(
        "accounts.Person",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    notes = models.TextField(blank=True)

    commission_calculation_type = models.CharField(
        max_length=8,
        choices=CommissionCalcType.choices,
        default=CommissionCalcType.PERCENT,
    )
    commission_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    commission_note = models.TextField(blank=True)

    tax_number = models.CharField(max_length=64, blank=True)
    tax_is_exempt = models.BooleanField(default=False)
    tax_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    bank_account_name = models.CharField(max_length=128, blank=True)
    bank_account_number = EncryptedTextField(blank=True, default="")
    bank_sort_code = EncryptedTextField(blank=True, default="")
    bank_iban = EncryptedTextField(blank=True, default="")
    bank_bic = EncryptedTextField(blank=True, default="")
    bank_name = models.CharField(max_length=128, blank=True)
    bank_address_line_1 = models.CharField(max_length=255, blank=True)
    bank_address_line_2 = models.CharField(max_length=255, blank=True)
    bank_post_code = models.CharField(max_length=32, blank=True)
    bank_city = models.CharField(max_length=128, blank=True)

    deposit_required = models.BooleanField(default=True)
    deposit_calculation_type = models.CharField(
        max_length=8,
        choices=DepositCalcType.choices,
        default=DepositCalcType.PERCENT,
    )
    deposit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=30,
    )
    interim_required = models.BooleanField(default=False)
    interim_calculation_type = models.CharField(
        max_length=8,
        choices=DepositCalcType.choices,
        default=DepositCalcType.PERCENT,
    )
    interim_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    days_interim_due_before_arrival = models.PositiveSmallIntegerField(default=0)
    days_balance_due_before_arrival = models.PositiveSmallIntegerField(default=60)

    security_deposit_required = models.BooleanField(default=False)
    security_deposit_calculation_type = models.CharField(
        max_length=8,
        choices=SecurityDepositCalcType.choices,
        default=SecurityDepositCalcType.FIXED,
    )
    security_deposit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    security_deposit_days_due_before_arrival = models.PositiveSmallIntegerField(default=14)
    security_deposit_days_refunded_after_departure = models.PositiveSmallIntegerField(default=7)
    security_deposit_payment_method = models.CharField(
        max_length=16,
        choices=SecurityDepositPaymentMethod.choices,
        default=SecurityDepositPaymentMethod.CARD_HOLD,
    )

    cancellation_fee_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    cancellation_fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    cancellation_window_days = models.PositiveSmallIntegerField(default=0)
    cancellation_notes = models.TextField(blank=True)

    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    def __str__(self) -> str:
        return f"Finance for group #{self.group_id}"
