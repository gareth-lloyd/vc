"""Payment serializer — both flat list/detail and nested track payments."""

from __future__ import annotations

from rest_framework import serializers

from payments.models import Payment


class PaymentSerializer(serializers.ModelSerializer[Payment]):
    """Full Payment row representation."""

    class Meta:
        model = Payment
        fields = [
            "id",
            "reference",
            "booking",
            "purpose",
            "status",
            "amount",
            "currency",
            "provider",
            "provider_reference",
            "payment_method",
            "due_at",
            "requested_at",
            "settled_at",
            "failure_reason",
            "meta",
            "concierge_item",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reference",
            "status",
            "settled_at",
            "failure_reason",
            "created_at",
            "updated_at",
        ]
