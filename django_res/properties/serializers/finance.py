"""Serializers for `PropertyFinance` and `GroupFinance`.

Bank-account fields (`bank_account_number`, `bank_sort_code`, `bank_iban`,
`bank_bic`) are encrypted at rest and **never echoed back** in API responses.
They are accepted on write only.
"""

from __future__ import annotations

from rest_framework import serializers

from properties.models import GroupFinance, PropertyFinance

_BANK_SECRET_FIELDS = (
    "bank_account_number",
    "bank_sort_code",
    "bank_iban",
    "bank_bic",
)

_FINANCE_FIELDS = (
    "commission_calculation_type",
    "commission_amount",
    "commission_note",
    "tax_number",
    "tax_is_exempt",
    "tax_percentage",
    "bank_account_name",
    "bank_account_number",
    "bank_sort_code",
    "bank_iban",
    "bank_bic",
    "bank_name",
    "bank_address_line_1",
    "bank_address_line_2",
    "bank_post_code",
    "bank_city",
    "deposit_required",
    "deposit_calculation_type",
    "deposit_amount",
    "interim_required",
    "interim_calculation_type",
    "interim_amount",
    "days_interim_due_before_arrival",
    "days_balance_due_before_arrival",
    "security_deposit_required",
    "security_deposit_calculation_type",
    "security_deposit_amount",
    "security_deposit_calculate_from",
    "security_deposit_days_due_before_arrival",
    "security_deposit_days_refunded_after_departure",
    "security_deposit_payment_method",
    "cancellation_fee_amount",
    "cancellation_fee_percent",
    "cancellation_window_days",
    "cancellation_notes",
    "notes",
)


class _FinanceBaseSerializer(serializers.ModelSerializer):
    """Drop encrypted bank fields from the serialized output."""

    def to_representation(self, instance):  # type: ignore[no-untyped-def]
        data = super().to_representation(instance)
        for field in _BANK_SECRET_FIELDS:
            data.pop(field, None)
        return data


class PropertyFinanceSerializer(_FinanceBaseSerializer):
    class Meta:
        model = PropertyFinance
        fields = ("property", *_FINANCE_FIELDS, "season", "contact", "parent")
        read_only_fields = ["property"]
        # Encrypted bank-secret fields are accepted on write but suppressed on
        # read by `_FinanceBaseSerializer.to_representation`.
        extra_kwargs = {f: {"write_only": False} for f in _BANK_SECRET_FIELDS}


class GroupFinanceSerializer(_FinanceBaseSerializer):
    class Meta:
        model = GroupFinance
        fields = ("group", *_FINANCE_FIELDS, "contact", "currency")
        read_only_fields = ["group"]
        extra_kwargs = {f: {"write_only": False} for f in _BANK_SECRET_FIELDS}
