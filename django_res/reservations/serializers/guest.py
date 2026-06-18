"""Guest serializers (full Guest rep + merge body).

The shallow Booking/Enquiry/Quotation history reps moved to
`serializers/contact.py` in `GAP-045` Unit 3d-1 (they are model-shaped, not
Guest-specific, and outlive Guest). They are re-exported here under their legacy
`Guest*` names so `GuestViewSet` keeps working until 3d-5 deletes `/guests`.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from reservations.enums import ContactMethod, GuestStatus
from reservations.models import Guest
from reservations.serializers.contact import (
    ContactBookingSerializer as GuestBookingSerializer,
)
from reservations.serializers.contact import (
    ContactEnquirySerializer as GuestEnquirySerializer,
)
from reservations.serializers.contact import (
    ContactQuotationSerializer as GuestQuotationSerializer,
)

__all__ = [
    "GuestBookingSerializer",
    "GuestEnquirySerializer",
    "GuestMergeSerializer",
    "GuestQuotationSerializer",
    "GuestSerializer",
]


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

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Mirror the DB CHECKs so the API returns a clean 400, not a 500.

        The two `guest_active_*` constraints are the hard floor; this is the
        friendly gate in front of them. Both are ACTIVE-only and computed on the
        *effective* row so partial updates are validated against the stored
        values they don't overwrite.
        """

        def effective(field: str, default: Any = None) -> Any:
            if field in attrs:
                return attrs[field]
            if self.instance is not None:
                return getattr(self.instance, field)
            return default

        if effective("status", GuestStatus.ACTIVE.value) != GuestStatus.ACTIVE.value:
            return attrs

        email = effective("email")
        phone = effective("phone", "")
        contact_method = effective("contact_method")

        if not email and not phone:
            raise serializers.ValidationError(
                "An active guest must be reachable by at least one channel (email or phone)."
            )
        if contact_method == ContactMethod.EMAIL.value and not email:
            raise serializers.ValidationError(
                {"contact_method": "Preferred method 'email' requires an email address."}
            )
        if contact_method in (ContactMethod.PHONE.value, ContactMethod.SMS.value) and not phone:
            raise serializers.ValidationError(
                {"contact_method": f"Preferred method '{contact_method}' requires a phone number."}
            )
        return attrs


class GuestMergeSerializer(serializers.Serializer[dict[str, Any]]):
    """Body for `POST /guests/{id}:merge` — target guest id to merge INTO."""

    target_guest_id = serializers.IntegerField()
