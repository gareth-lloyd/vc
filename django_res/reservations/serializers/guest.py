"""Guest serializers + shallow Booking/Enquiry/Quotation reps for nested lists."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from reservations.models import Booking, Enquiry, Guest, Quotation


class GuestSerializer(serializers.ModelSerializer[Guest]):
    """Full Guest representation."""

    # OneToOne to the swappable AUTH_USER_MODEL — read-only.
    user: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(
        read_only=True, allow_null=True
    )

    class Meta:
        model = Guest
        fields = [
            "id",
            "first_name",
            "last_name",
            "title",
            "email",
            "phone",
            "address_line_1",
            "address_line_2",
            "town",
            "post_code",
            "country",
            "contact_method",
            "marketing_consent",
            "notes",
            "status",
            "anonymized_at",
            "user",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "anonymized_at", "created_at", "updated_at"]


class GuestMergeSerializer(serializers.Serializer[dict[str, Any]]):
    """Body for `POST /guests/{id}:merge` — target guest id to merge INTO."""

    target_guest_id = serializers.IntegerField()


class GuestBookingSerializer(serializers.ModelSerializer[Booking]):
    """Shallow booking representation for `/guests/{id}/bookings`."""

    class Meta:
        model = Booking
        fields = [
            "id",
            "reference",
            "status",
            "property",
            "date_from",
            "date_to",
            "adults",
            "children",
            "is_archived",
            "created_at",
        ]
        read_only_fields = fields


class GuestEnquirySerializer(serializers.ModelSerializer[Enquiry]):
    class Meta:
        model = Enquiry
        fields = [
            "id",
            "reference",
            "status",
            "source",
            "request_type",
            "created_at",
        ]
        read_only_fields = fields


class GuestQuotationSerializer(serializers.ModelSerializer[Quotation]):
    class Meta:
        model = Quotation
        fields = [
            "id",
            "reference",
            "status",
            "expires_at",
            "created_at",
        ]
        read_only_fields = fields
