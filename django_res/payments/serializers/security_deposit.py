"""Security-deposit serializer — the SD row's own state for the wf-8 panel.

Distinct from `TrackSerializer` (a Payment aggregate shared by the deposit /
balance / security tracks): this exposes the `SecurityDeposit` row itself —
`kind`, `status`, `captured_amount`, `damage_claim` — which the operator panel
branches on. Read-only; all writes go through `SecurityDepositService`.
"""

from __future__ import annotations

from rest_framework import serializers

from payments.models import SecurityDeposit


class SecurityDepositSerializer(serializers.ModelSerializer[SecurityDeposit]):
    """Full read representation of a single `SecurityDeposit` row."""

    # Denormalised so the FE renders the currency without a second fetch; the
    # `damage_claim` FK serialises as its PK (the FE already holds the claim
    # list from `useBookingDamageClaims`).
    currency_code = serializers.CharField(source="currency.code", read_only=True)

    class Meta:
        model = SecurityDeposit
        fields = [
            "id",
            "reference",
            "kind",
            "status",
            "amount",
            "currency_code",
            "hold_expires_at",
            "due_at",
            "release_scheduled_for",
            "captured_amount",
            "refunded_amount",
            "damage_claim",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
