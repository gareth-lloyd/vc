"""Damage-claim serializers (BUG-008 / workflow 8)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from reservations.models import DamageClaim, DamageClaimPhoto


class DamageClaimPhotoSerializer(serializers.ModelSerializer[DamageClaimPhoto]):
    """Read representation of a damages evidence photo (wf8)."""

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = DamageClaimPhoto
        fields = ["id", "image_url", "caption", "created_at"]
        read_only_fields = fields

    def get_image_url(self, obj: DamageClaimPhoto) -> str | None:
        # Storage-generated: `/media/…` on local FileSystemStorage, an absolute
        # S3 URL on staging/prod — same convention as `PropertyImageSerializer`.
        if not obj.image:
            return None
        return obj.image.url


class DamageClaimSerializer(serializers.ModelSerializer[DamageClaim]):
    """Read representation."""

    currency_code = serializers.CharField(source="currency.code", read_only=True)
    photos = DamageClaimPhotoSerializer(many=True, read_only=True)

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

    def validate_itemized_lines(self, value: Any) -> list[dict[str, Any]]:
        # The model field is a bare JSONField (display-only breakdown). Guard
        # the shape the read side / FE iterates — a list of {label, amount} —
        # so a malformed blob can't persist into a money-bearing record.
        if not isinstance(value, list):
            raise serializers.ValidationError("Itemized lines must be a list.")
        for line in value:
            if not isinstance(line, dict) or "label" not in line or "amount" not in line:
                raise serializers.ValidationError(
                    "Each itemized line must be an object with 'label' and 'amount'."
                )
        return value
