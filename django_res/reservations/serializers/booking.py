"""Booking serializers — list / detail / write / notes."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from properties.models import PropertyFinance
from reservations.models import Booking, BookingEvent, BookingNote


class BookingListSerializer(serializers.ModelSerializer[Booking]):
    """Light booking representation for collection responses."""

    property_name = serializers.SerializerMethodField()
    guest_name = serializers.SerializerMethodField()
    currency_code = serializers.CharField(source="currency.code", read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "reference",
            "status",
            "property",
            "property_name",
            "guest",
            "guest_name",
            "agent",
            "assigned_to",
            "date_from",
            "date_to",
            "adults",
            "children",
            "currency",
            "currency_code",
            "rental_price",
            "balance_due",
            "balance_due_at",
            "site_source",
            "is_archived",
            "archived_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reference",
            "status",
            "property_name",
            "guest_name",
            "is_archived",
            "archived_at",
            "created_at",
            "updated_at",
        ]

    def get_property_name(self, obj: Booking) -> str | None:
        prop = obj.property
        if prop is None:
            return None
        return (prop.display_name or prop.name) or None

    def get_guest_name(self, obj: Booking) -> str | None:
        guest = obj.guest
        if guest is None:
            return None
        return f"{guest.first_name} {guest.last_name}".strip() or None


class BookingDetailSerializer(BookingListSerializer):
    """Detail view including pricing snapshot and lifecycle metadata."""

    owner = serializers.SerializerMethodField()
    commission = serializers.SerializerMethodField()

    class Meta(BookingListSerializer.Meta):
        fields = [
            *BookingListSerializer.Meta.fields,
            "quotation_line",
            "pricing_snapshot",
            "discount",
            "adjustment",
            "terms_version",
            "terms_accepted_at",
            "payment_method",
            "cancel_reason",
            "cancelled_at",
            "owner",
            "commission",
        ]

    # ------------------------------------------------------------------
    # Owner-tab payload — sourced from `property.finance.contact` and the
    # `PropertyFinance.effective()` property→group resolver. Both fields
    # tolerate the (very real) cases where `PropertyFinance` is missing or
    # has no contact assigned.
    # ------------------------------------------------------------------
    @staticmethod
    def _finance(obj: Booking) -> Any:
        try:
            return obj.property.finance
        except PropertyFinance.DoesNotExist:
            # OneToOne reverse access raises this when no finance row exists;
            # we treat that as "finance not configured". Any *other* exception
            # is a real bug and should propagate to a 500 rather than render
            # as an empty Owner tab.
            return None

    def get_owner(self, obj: Booking) -> dict[str, Any] | None:
        finance = self._finance(obj)
        if finance is None or finance.contact is None:
            return None
        contact = finance.contact
        # `BookingViewSet._detail_owner_qs` populates `primary_emails` /
        # `primary_phones` via `Prefetch(..., to_attr=...)`. Fall back to a
        # query when the serializer is instantiated without that queryset
        # (mostly tests that hand-construct a Booking).
        primary_emails = getattr(contact, "primary_emails", None)
        if primary_emails is None:
            primary_emails = list(contact.emails.filter(is_primary=True))
        primary_phones = getattr(contact, "primary_phones", None)
        if primary_phones is None:
            primary_phones = list(contact.phones.filter(is_primary=True))
        return {
            "id": contact.pk,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "company": contact.company,
            "primary_email": primary_emails[0].email if primary_emails else None,
            "primary_phone": primary_phones[0].number if primary_phones else None,
            "address_line_1": contact.address_line_1,
            "address_line_2": contact.address_line_2,
        }

    def get_commission(self, obj: Booking) -> dict[str, Any] | None:
        finance = self._finance(obj)
        if finance is None:
            return None
        commission = finance.effective_commission()
        amount = commission["amount"]
        return {
            "calculation_type": commission["calculation_type"] or None,
            "amount": f"{amount:.2f}" if amount is not None else None,
            # `effective()` returns "" for empty strings (its "no own value"
            # heuristic falls through to the group default). Coerce None → "".
            "note": commission["note"] or "",
        }


class BookingWriteSerializer(serializers.ModelSerializer[Booking]):
    """Booking update body. Most state lives on action endpoints."""

    class Meta:
        model = Booking
        fields = [
            "agent",
            "assigned_to",
            "site_source",
            "payment_method",
        ]


class BookingNoteSerializer(serializers.ModelSerializer[BookingNote]):
    """Operator-authored note on a booking."""

    class Meta:
        model = BookingNote
        fields = [
            "id",
            "booking",
            "author",
            "kind",
            "body",
            "is_pinned",
            "visibility",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "booking", "author", "created_at", "updated_at"]


class BookingEventSerializer(serializers.ModelSerializer[BookingEvent]):
    """Append-only activity row for the booking timeline."""

    class Meta:
        model = BookingEvent
        fields = [
            "id",
            "booking",
            "from_status",
            "to_status",
            "actor",
            "source",
            "reason",
            "meta",
            "created_at",
        ]
        read_only_fields = fields
