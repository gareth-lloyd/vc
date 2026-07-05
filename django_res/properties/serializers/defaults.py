"""Serializer for the `PropertyDefaults` singleton (GAP-070)."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import PropertyDefaults


class PropertyDefaultsSerializer(serializers.ModelSerializer[PropertyDefaults]):
    class Meta:
        model = PropertyDefaults
        fields = [
            "availability_default",
            "bookings_require_pre_approval",
            "requires_enquiry_first",
            "currency",
            "check_in_time",
            "check_out_time",
            "changeover_day",
            "min_nights_rental",
            "min_nights_rental_note",
            "prices_entered_as",
            "hold_duration_hours",
            "commission_calculation_type",
            "commission_amount",
            "commission_note",
            "tax_is_exempt",
            "tax_percentage",
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
            "security_deposit_days_due_before_arrival",
            "security_deposit_days_refunded_after_departure",
            "security_deposit_payment_method",
            "cancellation_fee_amount",
            "cancellation_fee_percent",
            "cancellation_window_days",
            "cancellation_notes",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]
