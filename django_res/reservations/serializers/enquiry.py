"""Enquiry serializers — list / detail / write / notes / events."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from reservations.models import Enquiry, EnquiryEvent, EnquiryNote
from reservations.serializers.quotation import QuotationDetailSerializer


class EnquiryListSerializer(serializers.ModelSerializer[Enquiry]):
    """Light representation for collection responses."""

    guest_name = serializers.SerializerMethodField()
    guest_email = serializers.SerializerMethodField()
    guest_phone = serializers.SerializerMethodField()
    guest_contact_method = serializers.SerializerMethodField()
    property_name = serializers.SerializerMethodField()
    region_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    agent_name = serializers.SerializerMethodField()

    class Meta:
        model = Enquiry
        fields = [
            "id",
            "reference",
            "status",
            "guest",
            "guest_name",
            "guest_email",
            "guest_phone",
            "guest_contact_method",
            "first_name",
            "last_name",
            "email",
            "phone",
            "contact_method",
            "property",
            "property_name",
            "region",
            "region_name",
            "date_from",
            "date_to",
            "adults",
            "children",
            "request_type",
            "assigned_to",
            "assigned_to_name",
            "agent",
            "agent_name",
            "site_source",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reference",
            "guest_name",
            "guest_email",
            "guest_phone",
            "guest_contact_method",
            "property_name",
            "region_name",
            "assigned_to_name",
            "agent_name",
            "created_at",
            "updated_at",
        ]

    def get_guest_name(self, obj: Enquiry) -> str | None:
        """Prefer the linked Guest's name; fall back to the denormalised
        first/last/email captured at lead time for anonymous submissions."""
        guest = obj.guest
        if guest is not None:
            name = f"{guest.first_name} {guest.last_name}".strip()
            if name:
                return name
        denorm = f"{obj.first_name} {obj.last_name}".strip()
        if denorm:
            return denorm
        return obj.email or None

    def get_guest_email(self, obj: Enquiry) -> str | None:
        guest = obj.guest
        if guest is None:
            return None
        return guest.email or None

    def get_guest_phone(self, obj: Enquiry) -> str | None:
        guest = obj.guest
        if guest is None:
            return None
        return guest.phone or None

    def get_guest_contact_method(self, obj: Enquiry) -> str | None:
        guest = obj.guest
        if guest is None:
            return None
        return guest.contact_method or None

    def get_property_name(self, obj: Enquiry) -> str | None:
        prop = obj.property
        if prop is None:
            return None
        return (prop.display_name or prop.name) or None

    def get_region_name(self, obj: Enquiry) -> str | None:
        region = obj.region
        return region.name if region is not None else None

    def get_assigned_to_name(self, obj: Enquiry) -> str | None:
        user = obj.assigned_to
        if user is None:
            return None
        full = user.get_full_name() if hasattr(user, "get_full_name") else ""
        return full.strip() or getattr(user, "email", None) or None

    def get_agent_name(self, obj: Enquiry) -> str | None:
        agent = obj.agent
        if agent is None:
            return None
        name = f"{agent.first_name} {agent.last_name}".strip()
        return name or agent.company or None


class EnquiryDetailSerializer(EnquiryListSerializer):
    """Full representation including the inbound message and flexible flag.

    Detail also exposes the quote-stack — every Quotation issued for this
    enquiry, with its lines — for the staff grouped-list UI, plus the
    `is_converted` rollup. The list serializer deliberately omits both so
    list responses stay slim.
    """

    quotations = QuotationDetailSerializer(many=True, read_only=True)
    is_converted = serializers.BooleanField(read_only=True)

    class Meta(EnquiryListSerializer.Meta):
        fields = [
            *EnquiryListSerializer.Meta.fields,
            "is_flexible",
            "flexibility_days",
            "min_bedrooms",
            "referral_code",
            "inbound_message",
            "quotations",
            "is_converted",
        ]


class EnquiryWriteSerializer(serializers.ModelSerializer[Enquiry]):
    """Create / update body. Status is read-only — use action endpoints."""

    class Meta:
        model = Enquiry
        fields = [
            "guest",
            "first_name",
            "last_name",
            "email",
            "phone",
            "contact_method",
            "property",
            "region",
            "date_from",
            "date_to",
            "is_flexible",
            "flexibility_days",
            "adults",
            "children",
            "min_bedrooms",
            "request_type",
            "referral_code",
            "agent",
            "assigned_to",
            "site_source",
            "inbound_message",
        ]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Enquiry dates are an optional, independent capture surface (the model
        # and spec leave them unconstrained), but an inverted range is never
        # meaningful: when both ends are known, the end must not precede the
        # start. Only judge the pair when the caller is actually writing a date
        # — otherwise a PATCH touching neither date would re-validate (and could
        # reject on) a pre-existing inverted pair the caller never sent. When
        # one date is written, fall back to the instance's stored other half.
        if "date_from" not in attrs and "date_to" not in attrs:
            return attrs
        date_from = attrs.get("date_from", getattr(self.instance, "date_from", None))
        date_to = attrs.get("date_to", getattr(self.instance, "date_to", None))
        if date_from and date_to and date_to < date_from:
            raise serializers.ValidationError(
                {"date_to": "The end date can't be before the start date."}
            )
        return attrs


class EnquiryNoteSerializer(serializers.ModelSerializer[EnquiryNote]):
    """Notes attached to an enquiry."""

    class Meta:
        model = EnquiryNote
        fields = [
            "id",
            "enquiry",
            "author",
            "kind",
            "body",
            "is_pinned",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "enquiry", "author", "created_at", "updated_at"]


class EnquiryEventSerializer(serializers.ModelSerializer[EnquiryEvent]):
    """Append-only activity row."""

    class Meta:
        model = EnquiryEvent
        fields = [
            "id",
            "enquiry",
            "from_status",
            "to_status",
            "kind",
            "actor",
            "source",
            "reason",
            "meta",
            "created_at",
        ]
        read_only_fields = fields
