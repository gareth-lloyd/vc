from __future__ import annotations

from django.apps import AppConfig


class PropertiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "properties"

    def ready(self) -> None:
        from core import audit
        from properties import signals  # noqa: F401
        from properties.models.finance import GroupFinance, PropertyFinance

        _SENSITIVE_BANK_FIELDS = (
            "bank_account_number",
            "bank_iban",
            "bank_bic",
            "bank_sort_code",
        )
        _AUDITED_FINANCE_FIELDS = (
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
        )
        audit.track(
            PropertyFinance,
            fields=_AUDITED_FINANCE_FIELDS,
            sensitive=_SENSITIVE_BANK_FIELDS,
        )
        audit.track(
            GroupFinance,
            fields=_AUDITED_FINANCE_FIELDS,
            sensitive=_SENSITIVE_BANK_FIELDS,
        )
