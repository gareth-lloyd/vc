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

from decimal import Decimal
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


# Final fallbacks for the nullable policy columns — the pre-GAP-070
# `GroupFinance` floor defaults, kept so a NULL on a row created outside
# `snapshot_defaults` (factories, lazy `get_or_create`) resolves the same way
# it always did. Real rows carry concrete values after freeze migration 0027.
# Deliberately NOT the `PropertyDefaults` values: that singleton seeds NEW
# properties (GAP-068 starter set — e.g. security_deposit_required=True there
# vs the False floor here) and is operator-editable; this dict is the frozen
# legacy floor and must stay behaviour-preserving.
_POLICY_FALLBACKS: dict[str, Any] = {
    "commission_calculation_type": CommissionCalcType.PERCENT,
    "commission_amount": Decimal("0"),
    "tax_is_exempt": False,
    "tax_percentage": Decimal("0"),
    "deposit_required": True,
    "deposit_calculation_type": DepositCalcType.PERCENT,
    "deposit_amount": Decimal("30"),
    "interim_required": False,
    "interim_calculation_type": DepositCalcType.PERCENT,
    "interim_amount": Decimal("0"),
    "days_interim_due_before_arrival": 0,
    "days_balance_due_before_arrival": 60,
    "security_deposit_required": False,
    "security_deposit_calculation_type": SecurityDepositCalcType.FIXED,
    "security_deposit_amount": Decimal("0"),
    "security_deposit_days_due_before_arrival": 14,
    "security_deposit_days_refunded_after_departure": 7,
    "security_deposit_payment_method": SecurityDepositPaymentMethod.CARD_HOLD,
    "cancellation_fee_amount": Decimal("0"),
    "cancellation_fee_percent": Decimal("0"),
    "cancellation_window_days": 0,
}


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
    def _policy(self, field: str) -> Any:
        """Own value, falling back to the pre-GAP-070 policy floor when NULL.

        Post-freeze (migration 0027) real rows carry concrete values; the
        fallback only covers rows created outside `snapshot_defaults`
        (factories, lazy `get_or_create`) where a column can still be NULL.
        The `!= ""` guard mirrors the old `effective()` contract for the
        nullable choice columns, where a raw write can land "".
        """
        own = getattr(self, field)
        if own is not None and own != "":
            return own
        return _POLICY_FALLBACKS[field]

    def effective_commission(self) -> dict[str, Any]:
        return {
            "calculation_type": self._policy("commission_calculation_type"),
            "amount": self._policy("commission_amount"),
            "note": self.commission_note,
        }

    def effective_tax_policy(self) -> dict[str, Any]:
        return {
            "tax_number": self.tax_number,
            "is_exempt": self._policy("tax_is_exempt"),
            "percentage": self._policy("tax_percentage"),
        }

    def effective_payment_schedule(self) -> dict[str, Any]:
        return {
            "deposit_required": self._policy("deposit_required"),
            "deposit_calculation_type": self._policy("deposit_calculation_type"),
            "deposit_amount": self._policy("deposit_amount"),
            "interim_required": self._policy("interim_required"),
            "interim_calculation_type": self._policy("interim_calculation_type"),
            "interim_amount": self._policy("interim_amount"),
            "days_interim_due_before_arrival": self._policy("days_interim_due_before_arrival"),
            "days_balance_due_before_arrival": self._policy("days_balance_due_before_arrival"),
        }

    def effective_security_deposit_policy(self) -> dict[str, Any]:
        return {
            "required": self._policy("security_deposit_required"),
            "calculation_type": self._policy("security_deposit_calculation_type"),
            "amount": self._policy("security_deposit_amount"),
            "days_due_before_arrival": self._policy(
                "security_deposit_days_due_before_arrival",
            ),
            "days_refunded_after_departure": self._policy(
                "security_deposit_days_refunded_after_departure",
            ),
            "payment_method": self._policy("security_deposit_payment_method"),
        }

    def effective_bank_account(self) -> dict[str, Any]:
        return {
            "account_name": self.bank_account_name,
            "account_number": self.bank_account_number,
            "sort_code": self.bank_sort_code,
            "iban": self.bank_iban,
            "bic": self.bank_bic,
            "bank_name": self.bank_name,
            "address_line_1": self.bank_address_line_1,
            "address_line_2": self.bank_address_line_2,
            "post_code": self.bank_post_code,
            "city": self.bank_city,
        }

    def effective_cancellation_policy(self) -> dict[str, Any]:
        return {
            "fee_amount": self._policy("cancellation_fee_amount"),
            "fee_percent": self._policy("cancellation_fee_percent"),
            "window_days": self._policy("cancellation_window_days"),
            "notes": self.cancellation_notes,
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
