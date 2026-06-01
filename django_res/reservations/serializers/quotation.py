"""Quotation + QuotationLine serializers."""

from __future__ import annotations

from rest_framework import serializers

from reservations.models import Quotation, QuotationLine


class QuotationLineSerializer(serializers.ModelSerializer[QuotationLine]):
    """Read representation of a quotation line."""

    property_name = serializers.SerializerMethodField()
    hero_image_url = serializers.SerializerMethodField()

    class Meta:
        model = QuotationLine
        fields = [
            "id",
            "quotation",
            "property",
            "property_name",
            "hero_image_url",
            "date_from",
            "date_to",
            "adults",
            "children",
            "pricing_snapshot",
            "total",
            "discount",
            "inclusions",
            "price_override_reason",
            "is_selected",
            "is_manual",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "quotation",
            "property_name",
            "hero_image_url",
            "pricing_snapshot",
            "total",
            "discount",
            "inclusions",
            "price_override_reason",
            "is_selected",
            "created_at",
            "updated_at",
        ]

    def get_property_name(self, obj: QuotationLine) -> str | None:
        prop = obj.property
        if prop is None:
            return None
        return (prop.display_name or prop.name) or None

    def get_hero_image_url(self, obj: QuotationLine) -> str | None:
        prop = obj.property
        if prop is None:
            return None
        return prop.hero_image_url()


class QuotationLineWriteSerializer(serializers.ModelSerializer[QuotationLine]):
    """Write body for a line.

    Non-manual lines are priced server-side (engine total, minus `discount`).
    Manual lines (`is_manual=True`) honour the operator-supplied `total` and
    REQUIRE a `price_override_reason` for the audit trail.
    """

    class Meta:
        model = QuotationLine
        fields = [
            "property",
            "date_from",
            "date_to",
            "adults",
            "children",
            "discount",
            "inclusions",
            "is_manual",
            "total",
            "price_override_reason",
            "notes",
        ]

    def validate(self, attrs: dict) -> dict:
        # On a partial update the incoming `is_manual` may be absent; fall back
        # to the instance so a PATCH that only edits the total/reason is judged
        # against the line's real manual state.
        is_manual = attrs.get("is_manual")
        if is_manual is None and self.instance is not None:
            is_manual = self.instance.is_manual
        if is_manual:
            reason = attrs.get("price_override_reason")
            if reason is None and self.instance is not None:
                reason = self.instance.price_override_reason
            if not (reason or "").strip():
                raise serializers.ValidationError(
                    {"price_override_reason": ["This field is required for a manual line."]}
                )
        return attrs


class QuotationListSerializer(serializers.ModelSerializer[Quotation]):
    """Light header representation."""

    # Surface the ISO code, not the FK PK — the FE renders this as text in
    # lists and feeds it into formatMoney() for inline price display.
    currency: serializers.SlugRelatedField = serializers.SlugRelatedField(
        slug_field="code", read_only=True
    )
    guest_name = serializers.SerializerMethodField()
    enquiry_reference = serializers.SerializerMethodField()
    agent_name = serializers.SerializerMethodField()

    class Meta:
        model = Quotation
        fields = [
            "id",
            "reference",
            "enquiry",
            "enquiry_reference",
            "guest",
            "guest_name",
            "agent",
            "agent_name",
            "currency",
            "status",
            "expires_at",
            "is_unbranded",
            "terms_version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reference",
            "enquiry_reference",
            "guest_name",
            "agent_name",
            "created_at",
            "updated_at",
        ]

    def get_guest_name(self, obj: Quotation) -> str | None:
        guest = obj.guest
        if guest is None:
            return None
        return f"{guest.first_name} {guest.last_name}".strip() or None

    def get_enquiry_reference(self, obj: Quotation) -> str | None:
        enquiry = obj.enquiry
        return enquiry.reference if enquiry is not None else None

    def get_agent_name(self, obj: Quotation) -> str | None:
        agent = obj.agent
        if agent is None:
            return None
        # Contact has first_name/last_name; fall back to company if both blank.
        name = f"{agent.first_name} {agent.last_name}".strip()
        return name or agent.company or None


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
