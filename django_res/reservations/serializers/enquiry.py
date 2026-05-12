"""Enquiry serializers — list / detail / write / notes / events."""

from __future__ import annotations

from rest_framework import serializers

from reservations.models import Enquiry, EnquiryEvent, EnquiryNote


class EnquiryListSerializer(serializers.ModelSerializer[Enquiry]):
    """Light representation for collection responses."""

    class Meta:
        model = Enquiry
        fields = [
            "id",
            "reference",
            "status",
            "guest",
            "first_name",
            "last_name",
            "email",
            "property",
            "region",
            "date_from",
            "date_to",
            "adults",
            "children",
            "request_type",
            "assigned_to",
            "agent",
            "site_source",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "reference", "created_at", "updated_at"]


class EnquiryDetailSerializer(EnquiryListSerializer):
    """Full representation including the inbound message and flexible flag."""

    class Meta(EnquiryListSerializer.Meta):
        fields = [
            *EnquiryListSerializer.Meta.fields,
            "is_flexible",
            "min_bedrooms",
            "referral_code",
            "inbound_message",
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
            "property",
            "region",
            "date_from",
            "date_to",
            "is_flexible",
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
