"""Booking serializers — list / detail / write / notes."""

from __future__ import annotations

from rest_framework import serializers

from reservations.models import Booking, BookingEvent, BookingNote


class BookingListSerializer(serializers.ModelSerializer[Booking]):
    """Light booking representation for collection responses."""

    currency_code = serializers.CharField(source="currency.code", read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "reference",
            "status",
            "property",
            "guest",
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
            "is_archived",
            "archived_at",
            "created_at",
            "updated_at",
        ]


class BookingDetailSerializer(BookingListSerializer):
    """Detail view including pricing snapshot and lifecycle metadata."""

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
        ]


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
