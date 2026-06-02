"""Quotation + QuotationLine serializers."""

from __future__ import annotations

from rest_framework import serializers

from reservations.models import Quotation, QuotationLine


class QuotationLineSerializer(serializers.ModelSerializer[QuotationLine]):
    """Read representation of a quotation line."""

    property_name = serializers.SerializerMethodField()
    hero_image_url = serializers.SerializerMethodField()
    # The original arrival when the engine nudged it forward to the property's
    # changeover day (GAP-007). `null` when the dates weren't moved. The FE
    # renders the "we moved your dates" note from this + `date_from`.
    changeover_shifted_from = serializers.SerializerMethodField()

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
            "changeover_shifted_from",
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
            "changeover_shifted_from",
            "pricing_snapshot",
            "total",
            "discount",
            "inclusions",
            "price_override_reason",
            "is_selected",
            "created_at",
            "updated_at",
        ]

    def get_changeover_shifted_from(self, obj: QuotationLine) -> str | None:
        snapshot = obj.pricing_snapshot or {}
        return snapshot.get("changeover_shifted_from")

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

    # Accept a blank/absent `total` at the field layer (the FE sends `""` when
    # the operator clears the field) so the manual-line presence check lands in
    # `validate()` as an explicit, i18n-agnostic field error rather than DRF's
    # generic "A valid number is required." For a non-manual line the supplied
    # total is server-recomputed by `_reprice` regardless.
    total = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
    )

    def to_internal_value(self, data: dict) -> dict:
        # Coerce an empty-string `total` to None so the DecimalField doesn't
        # reject it field-level; the manual-vs-not rule is decided in validate.
        if isinstance(data, dict) and data.get("total") == "":
            data = {**data, "total": None}
        return super().to_internal_value(data)

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
            # A manual line owns its `total` — it must be a present, positive
            # value. Raise an explicit, i18n-agnostic field error here rather
            # than letting a blank/absent total fall through to the engine
            # (which would silently 0-default) or to DRF's generic "A valid
            # number is required." On a partial update fall back to the
            # instance, mirroring the reason check above.
            total = attrs.get("total")
            if total is None and self.instance is not None and "total" not in attrs:
                total = self.instance.total
            if total is None or total <= 0:
                raise serializers.ValidationError(
                    {"total": ["This field is required for a manual line."]}
                )
        elif attrs.get("total") is None:
            # Non-manual line: `total` is server-recomputed by `_reprice`. Drop
            # an explicit None so it never reaches the non-nullable model field;
            # the model default / repricing supplies the real value.
            attrs.pop("total", None)
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
