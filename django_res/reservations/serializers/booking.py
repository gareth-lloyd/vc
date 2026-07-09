"""Booking serializers — list / detail / write / notes."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import models
from rest_framework import serializers

from accounts.models import User
from core.api.permissions import NON_OPERATOR_ASSIGNEE_MSG, is_assignable_operator
from properties.enums import PriceBasis
from properties.models import PropertyFinance, PropertySettings
from reservations.models import Booking, BookingEvent, BookingNote
from reservations.serializers._contact_reads import contact_email, contact_name
from reservations.services.charges import (
    charges_owner_adjustments,
    charges_total_for,
    effective_commission_for,
)


class BookingListSerializer(serializers.ModelSerializer[Booking]):
    """Light booking representation for collection responses."""

    property_name = serializers.SerializerMethodField()
    guest_name = serializers.SerializerMethodField()
    guest_email = serializers.SerializerMethodField()
    night_count = serializers.SerializerMethodField()
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    # `balance_due` holds the denormalised engine-gross total (07-payments.md)
    # — it is *not* decremented as payments settle, and a re-price rewrites it
    # without touching manual charge items. What the guest actually owes is
    # `balance_due` plus the live Σ of charge items, exposed here as `total`
    # so the FE never reconstructs the gross from net-of-commission
    # `rental_price`.
    total = serializers.SerializerMethodField()
    amount_paid = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "reference",
            "status",
            "property",
            "property_name",
            "guest_name",
            "guest_email",
            "agent",
            "assigned_to",
            "date_from",
            "date_to",
            "night_count",
            "adults",
            "children",
            "currency",
            "currency_code",
            "rental_price",
            "total",
            "amount_paid",
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
            "guest_email",
            "night_count",
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
        return contact_name(obj.person)

    def get_guest_email(self, obj: Booking) -> str | None:
        return contact_email(obj.person)

    def get_night_count(self, obj: Booking) -> int:
        return (obj.date_to - obj.date_from).days

    @staticmethod
    def _charges_total(obj: Booking) -> Decimal:
        return charges_total_for(obj)

    def get_total(self, obj: Booking) -> str:
        return f"{(obj.balance_due + self._charges_total(obj)):.2f}"

    def get_amount_paid(self, obj: Booking) -> str:
        """Settled rental money (SUCCEEDED deposit/balance payments).

        Security-deposit holds and concierge invoices settle on their own
        tracks and are excluded from rental maths (07-payments.md). The
        statuses/purposes are string literals because `reservations` sits
        below `payments` in the import spine and must not import its enums.
        """
        paid = getattr(obj, "amount_paid_total", None)
        if paid is None:
            paid = obj.payments.filter(
                status="succeeded", purpose__in=("deposit", "balance")
            ).aggregate(total=models.Sum("amount"))["total"]
        return f"{paid or Decimal('0'):.2f}"


class BookingDetailSerializer(BookingListSerializer):
    """Detail view including pricing snapshot and lifecycle metadata."""

    owner = serializers.SerializerMethodField()
    commission = serializers.SerializerMethodField()
    prices_entered_as = serializers.SerializerMethodField()
    net_to_owner = serializers.SerializerMethodField()
    charges_total = serializers.SerializerMethodField()

    class Meta(BookingListSerializer.Meta):
        fields = [
            *BookingListSerializer.Meta.fields,
            "quotation_line",
            "pricing_snapshot",
            "charges_total",
            "discount",
            "adjustment",
            "terms_version",
            "terms_accepted_at",
            "payment_method",
            "cancel_reason",
            "cancelled_at",
            "owner",
            "commission",
            "prices_entered_as",
            "net_to_owner",
        ]

    # ------------------------------------------------------------------
    # Owner-tab payload — sourced from `property.finance.contact` and the
    # `PropertyFinance.effective_*()` resolvers. Both fields tolerate the
    # (very real) cases where `PropertyFinance` is missing or has no contact
    # assigned.
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
            "company": contact.agency_name,
            "primary_email": primary_emails[0].email if primary_emails else None,
            "primary_phone": primary_phones[0].number if primary_phones else None,
            "address_line_1": contact.address_line_1,
            "address_line_2": contact.address_line_2,
        }

    def get_charges_total(self, obj: Booking) -> str:
        return f"{self._charges_total(obj):.2f}"

    @classmethod
    def _effective_commission(cls, obj: Booking) -> dict[str, Any] | None:
        return effective_commission_for(obj)

    def get_commission(self, obj: Booking) -> dict[str, Any] | None:
        commission = self._effective_commission(obj)
        if commission is None:
            return None
        amount = commission["amount"]
        return {
            "calculation_type": commission["calculation_type"] or None,
            "amount": f"{amount:.2f}" if amount is not None else None,
            # The note is a blank-capable TextField; coerce None → "".
            "note": commission["note"] or "",
        }

    # ------------------------------------------------------------------
    # Owner-facing rate basis + net-to-owner — `09-departures.md`
    # correctness fix. The UI labels the rate column using the effective
    # `prices_entered_as` flag, and renders the owner statement from
    # `net_to_owner` rather than the gross `rental_price` figure.
    # ------------------------------------------------------------------
    @staticmethod
    def _effective_prices_entered_as(obj: Booking) -> str | None:
        """Resolve the `prices_entered_as` basis for the booking's property.

        Reads `PropertySettings.prices_entered_as` directly, defaulting a
        NULL to GROSS (the pre-GAP-070 group-floor default). Returns None
        only when no settings row exists (legacy/import edge case); callers
        treat None as "unknown — let the UI fall back to gross".
        """
        prop = obj.property
        if prop is None:
            return None
        try:
            settings_ = prop.settings
        except PropertySettings.DoesNotExist:
            return None
        return settings_.prices_entered_as or PriceBasis.GROSS.value

    def get_prices_entered_as(self, obj: Booking) -> str | None:
        return self._effective_prices_entered_as(obj)

    def get_net_to_owner(self, obj: Booking) -> dict[str, Any] | None:
        """Render owner-net from `Booking.pricing_snapshot` + charge items.

        `PricingEngine.quote` writes `net_to_owner` directly into the
        snapshot, so the primary path just reads it. The serializer never
        recomputes snapshot money — but manual charge items live outside
        the immutable snapshot, so their owner/agency split (legacy-style:
        charges enter the commissionable base, see `services.charges`) is
        layered on at read time.
        """
        snapshot = obj.pricing_snapshot or {}
        try:
            total = Decimal(str(snapshot["total"]))
            commission = Decimal(str(snapshot["commission"]))
            tax = Decimal(str(snapshot["tax"]))
        except (KeyError, InvalidOperation, TypeError):
            return None
        # Legacy-snapshot fallback: rows imported by `data_migration` carry
        # `pricing_snapshot = {}` (handled above by the KeyError guard) and
        # any rebuild-era snapshot pre-dating this engine change lacks the
        # `net_to_owner` key. Compute it from `total - commission - tax` so
        # those bookings still render. New snapshots take the fast path.
        raw_net = snapshot.get("net_to_owner")
        if raw_net is not None:
            try:
                net = Decimal(str(raw_net)).quantize(Decimal("0.01"))
            except (InvalidOperation, TypeError):
                net = (total - commission - tax).quantize(Decimal("0.01"))
        else:
            net = (total - commission - tax).quantize(Decimal("0.01"))
        # GAP-076: the charge arithmetic is shared with the owner API
        # (`charges_owner_adjustments`) so the two surfaces always agree.
        adjust = charges_owner_adjustments(obj)
        total += adjust.gross_delta
        commission += adjust.commission_delta
        net += adjust.net_delta
        currency_code = obj.currency.code if obj.currency_id else None
        return {
            "currency_code": currency_code,
            "gross_total": f"{total:.2f}",
            "commission": f"{commission:.2f}",
            "tax": f"{tax:.2f}",
            "net_to_owner": f"{net:.2f}",
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

    def validate_assigned_to(self, value: User | None) -> User | None:
        # Server-side enforcement of the assignable-operator rule — the API
        # must not trust the FE picker. Unassign (None) always allowed.
        if value is not None and not is_assignable_operator(value):
            raise serializers.ValidationError(NON_OPERATOR_ASSIGNEE_MSG)
        return value


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
