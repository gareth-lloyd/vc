"""Refund serializers — list/detail + the create request body."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from payments.models import Refund
from pricing.models import Currency


class RefundSerializer(serializers.ModelSerializer[Refund]):
    """Full Refund row representation."""

    class Meta:
        model = Refund
        fields = [
            "id",
            "reference",
            "booking",
            "against_payment",
            "purpose_track",
            "amount",
            "currency",
            "status",
            "reason_code",
            "reason_notes",
            "method",
            "requested_by",
            "requested_at",
            "approved_by",
            "approved_at",
            "rejected_by",
            "rejected_at",
            "rejection_reason",
            "executed_by",
            "executed_at",
            "cancelled_at",
            "settled_at",
            "failure_reason",
            "meta",
            "security_deposit",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reference",
            "status",
            "approved_by",
            "approved_at",
            "rejected_by",
            "rejected_at",
            "rejection_reason",
            "executed_by",
            "executed_at",
            "cancelled_at",
            "settled_at",
            "failure_reason",
            "requested_by",
            "requested_at",
            "created_at",
            "updated_at",
        ]


class RefundRequestSerializer(serializers.Serializer[None]):
    """Body shape for `POST /bookings/{id}/refunds`."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(), required=False, allow_null=True
    )
    purpose_track = serializers.CharField()
    reason_code = serializers.CharField()
    reason_notes = serializers.CharField(required=False, allow_blank=True)
    method = serializers.CharField(required=False)
    against_payment = serializers.IntegerField(required=False, allow_null=True)
    # Operator UIs that may retry (double-click, flaky network) send a key;
    # a repeat POST with the same key returns the original row (FG-010).
    idempotency_key = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=128
    )
