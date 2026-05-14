"""Quotation + QuotationLine serializers."""

from __future__ import annotations

from rest_framework import serializers

from reservations.models import Quotation, QuotationLine


class QuotationLineSerializer(serializers.ModelSerializer[QuotationLine]):
    """Read representation of a quotation line."""

    class Meta:
        model = QuotationLine
        fields = [
            "id",
            "quotation",
            "property",
            "date_from",
            "date_to",
            "adults",
            "children",
            "pricing_snapshot",
            "total",
            "is_selected",
            "is_manual",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "quotation",
            "pricing_snapshot",
            "total",
            "is_selected",
            "created_at",
            "updated_at",
        ]


class QuotationLineWriteSerializer(serializers.ModelSerializer[QuotationLine]):
    """Write body for a line — pricing is recomputed server-side."""

    class Meta:
        model = QuotationLine
        fields = [
            "property",
            "date_from",
            "date_to",
            "adults",
            "children",
            "is_manual",
            "notes",
        ]


class QuotationListSerializer(serializers.ModelSerializer[Quotation]):
    """Light header representation."""

    # Surface the ISO code, not the FK PK — the FE renders this as text in
    # lists and feeds it into formatMoney() for inline price display.
    currency: serializers.SlugRelatedField = serializers.SlugRelatedField(
        slug_field="code", read_only=True
    )

    class Meta:
        model = Quotation
        fields = [
            "id",
            "reference",
            "enquiry",
            "guest",
            "agent",
            "currency",
            "status",
            "expires_at",
            "is_unbranded",
            "terms_version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "reference", "created_at", "updated_at"]


class QuotationDetailSerializer(QuotationListSerializer):
    """Detail view with inlined lines and cancel reason."""

    lines = QuotationLineSerializer(many=True, read_only=True)

    class Meta(QuotationListSerializer.Meta):
        fields = [*QuotationListSerializer.Meta.fields, "cancel_reason", "lines"]


class QuotationWriteSerializer(serializers.ModelSerializer[Quotation]):
    """Header write body. Status is action-driven."""

    class Meta:
        model = Quotation
        fields = [
            "enquiry",
            "guest",
            "agent",
            "currency",
            "is_unbranded",
            "expires_at",
            "terms_version",
        ]
