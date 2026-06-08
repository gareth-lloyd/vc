"""Guest serializers + shallow Booking/Enquiry/Quotation reps for nested lists."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from reservations.enums import ContactMethod, GuestStatus, QuotationStatus
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
    """Enquiry history row for `/guests/{id}/enquiries`, enriched with the
    real quote count and the converted booking (if any).

    Both computed fields read off `obj.quotations.all()` — never a fresh
    `.filter()` — so they reuse the 3-level prefetch the viewset installs
    (`GuestViewSet.enquiries`) and stay query-bounded. When the cache is not
    primed they fall back to live SELECTs and remain correct.

    `quote_count` and the converted-booking walk exclude `booking-`-prefixed
    synthetic quotations (the BookingLoader legacy-fill rows) — those leak into
    no public API and would otherwise inflate the count / mis-attribute a
    conversion.

    `converted_booking` rule: among this enquiry's ACCEPTED quotations'
    selected lines, the *most-recently-created non-archived* Booking; `null` if
    none. Plural/ambiguous graphs (re-books, cancellations) collapse to the
    live booking, never a superseded one.
    """

    quote_count = serializers.SerializerMethodField()
    converted_booking = serializers.SerializerMethodField()

    class Meta:
        model = Enquiry
        fields = [
            "id",
            "reference",
            "status",
            "site_source",
            "request_type",
            "created_at",
            "quote_count",
            "converted_booking",
        ]
        read_only_fields = [
            "id",
            "reference",
            "status",
            "site_source",
            "request_type",
            "created_at",
        ]

    @staticmethod
    def _real_quotations(obj: Enquiry) -> list[Quotation]:
        return [q for q in obj.quotations.all() if not (q.legacy_id or "").startswith("booking-")]

    def get_quote_count(self, obj: Enquiry) -> int:
        return len(self._real_quotations(obj))

    def get_converted_booking(self, obj: Enquiry) -> dict[str, Any] | None:
        accepted = QuotationStatus.ACCEPTED.value
        bookings = [
            booking
            for quotation in self._real_quotations(obj)
            if quotation.status == accepted
            for line in quotation.lines.all()
            if line.is_selected
            for booking in line.bookings.all()
            if not booking.is_archived
        ]
        if not bookings:
            return None
        best = max(bookings, key=lambda b: b.created_at)
        return {"reference": best.reference, "status": best.status}


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
