"""Damage-claim serializers (BUG-008 / workflow 8)."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from reservations.models import DamageClaim


class DamageClaimSerializer(serializers.ModelSerializer[DamageClaim]):
    """Read representation."""

    currency_code = serializers.CharField(source="currency.code", read_only=True)

    class Meta:
        model = DamageClaim
        fields = [
            "id",
            "reference",
            "booking",
            "currency",
            "currency_code",
            "amount",
            "description",
            "status",
            "itemized_lines",
            "photos",
            "accepted_by_guest_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DamageClaimWriteSerializer(serializers.ModelSerializer[DamageClaim]):
    """Write body. `currency` is optional — the service defaults it to the
    booking's and rejects a mismatch. `itemized_lines` is a free-form JSON
    scaffold (a display-only breakdown; it need not reconcile to `amount`)."""

    class Meta:
        model = DamageClaim
        fields = [
            "amount",
            "description",
            "currency",
            "itemized_lines",
        ]
        extra_kwargs = {
            "currency": {"required": False},
            "itemized_lines": {"required": False},
        }

    def validate_amount(self, value: Decimal) -> Decimal:
        # Surface the model's `amount > 0` constraint as a 400 field error
        # instead of a 500 IntegrityError (claims are never negative).
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value
