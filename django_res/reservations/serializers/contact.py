"""Shallow Booking/Enquiry/Quotation/TravelPreference reps for the Person-scoped
customer history reads (`/contacts/{id}/...`).

`GAP-045` Unit 3d-1: these are model-shaped (not customer-identity specific), so
they were lifted out of `serializers/guest.py` to outlive the Guest retirement.
`serializers/guest.py` keeps `Guest*`-named aliases until 3d-5 deletes
`/guests`.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from reservations.enums import QuotationStatus
from reservations.models import Booking, Enquiry, GuestPreference, Quotation


class ContactBookingSerializer(serializers.ModelSerializer[Booking]):
    """Shallow booking representation for `/contacts/{id}/bookings`."""

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


class ContactEnquirySerializer(serializers.ModelSerializer[Enquiry]):
    """Enquiry history row for `/contacts/{id}/enquiries`, enriched with the
    real quote count and the converted booking (if any).

    Both computed fields read off `obj.quotations.all()` — never a fresh
    `.filter()` — so they reuse the 3-level prefetch the viewset installs and
    stay query-bounded. When the cache is not primed they fall back to live
    SELECTs and remain correct.

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
        # Single source of truth for the synthetic-row exclusion: the
        # `.real()` queryset method (SMELL-014). When the viewset primed the
        # prefetch its cache is already `.real()`-filtered, so reuse it and stay
        # query-bounded; on the unprimed fallback hit the DB through `.real()`
        # so `booking-` synthetic rows can never leak there either — no
        # hand-rolled predicate.
        if "quotations" in getattr(obj, "_prefetched_objects_cache", {}):
            return list(obj.quotations.all())
        return list(obj.quotations.real())

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


class ContactQuotationSerializer(serializers.ModelSerializer[Quotation]):
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


class ContactTravelPreferenceSerializer(serializers.ModelSerializer[GuestPreference]):
    """Shallow travel-preference row for `/contacts/{id}/travel-preferences`."""

    preference_type = serializers.CharField(source="preference_type.name", read_only=True)

    class Meta:
        model = GuestPreference
        fields = [
            "id",
            "preference_type",
            "notes",
            "quotation",
            "created_at",
        ]
        read_only_fields = fields
