"""Enquiry serializers — list / detail / write / notes / events."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from accounts.models import User
from core.api.permissions import NON_OPERATOR_ASSIGNEE_MSG, is_assignable_operator
from reservations.enums import EnquiryStatus, QuotationStatus
from reservations.models import Enquiry, EnquiryEvent, EnquiryNote
from reservations.serializers._contact_reads import contact_email, contact_name, contact_phone
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
            "lead_status",
            "lost_reason",
            "person",
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
            "is_flexible",
            "flexibility_days",
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
            "lead_status",
            "lost_reason",
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
        """Prefer the unified Person, then the denormalised first/last/email
        captured at lead time for anonymous submissions (an enquiry can have no
        customer — `person` is nullable — so the denorm leg stays)."""
        name = contact_name(obj.person)
        if name:
            return name
        denorm = f"{obj.first_name} {obj.last_name}".strip()
        if denorm:
            return denorm
        return obj.email or None

    def get_guest_email(self, obj: Enquiry) -> str | None:
        return contact_email(obj.person)

    def get_guest_phone(self, obj: Enquiry) -> str | None:
        return contact_phone(obj.person)

    def get_guest_contact_method(self, obj: Enquiry) -> str | None:
        # GAP-045 Unit 3d-3: contact_method resolves solely from the unified
        # Person's `preferred_method` (the guest fallback was removed). The
        # mirror coerced a null guest contact_method to "email" (the field's
        # default), so a saved customer always reports a method; an anonymous
        # enquiry with no person reports None.
        person = obj.person
        if person is not None and person.preferred_method:
            return person.preferred_method
        return None

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
        return name or agent.agency_name or None


class EnquiryDetailSerializer(EnquiryListSerializer):
    """Full representation including the inbound message and flexible flag.

    Detail also exposes the quote-stack — every Quotation issued for this
    enquiry, with its lines — for the staff grouped-list UI, plus the
    `is_converted` rollup. The list serializer deliberately omits both so
    list responses stay slim.
    """

    quotations = QuotationDetailSerializer(many=True, read_only=True)
    is_converted = serializers.BooleanField(read_only=True)
    quotes_to_convert = serializers.SerializerMethodField()

    class Meta(EnquiryListSerializer.Meta):
        fields = [
            *EnquiryListSerializer.Meta.fields,
            # is_flexible / flexibility_days now ride the list serializer (the
            # GAP-039 Flex? column needs them) — inherited here, not re-declared.
            "min_bedrooms",
            "referral_code",
            "inbound_message",
            "quotations",
            "is_converted",
            "quotes_to_convert",
        ]

    def get_quotes_to_convert(self, obj: Enquiry) -> int | None:
        """GAP-038 conversion metric: how many real operator quotes it took to win
        this enquiry — the count of real quotes issued up to and including the
        accepted one (the first ACCEPTED quote ordered by ``(created_at, pk)``).

        Only meaningful for a CONVERTED enquiry that has an accepted real quote;
        otherwise ``None``. (Legacy bookings migrate as NEW enquiries with a
        single synthetic DRAFT quote, so they read null — the metric covers
        rebuild-era conversions only.)

        Computed in pure Python over the already-prefetched ``obj.quotations`` —
        the detail prefetch is ``Quotation.objects.real()``, so synthetic
        ``booking-`` rows are excluded and no extra query is issued. This relies
        on the serializer only ever running against the prefetched detail
        queryset: GET-detail uses ``EnquiryViewSet.get_queryset``'s prefetch, and
        the write/action responses re-fetch through ``_detail_response`` (the
        ``:convert`` action in particular, because ``convert()`` →
        ``refresh_locked()`` wipes the instance's prefetch cache). pk is the
        tie-break because ``(created_at, pk)`` is a total order — no
        single-ACCEPTED row is DB-enforced.
        """
        if obj.status != EnquiryStatus.CONVERTED.value:
            return None
        quotes = sorted(obj.quotations.all(), key=lambda q: (q.created_at, q.pk))
        accepted_index = next(
            (i for i, q in enumerate(quotes) if q.status == QuotationStatus.ACCEPTED.value),
            None,
        )
        if accepted_index is None:
            return None
        return accepted_index + 1


class EnquiryWriteSerializer(serializers.ModelSerializer[Enquiry]):
    """Create / update body. Status is read-only — use action endpoints."""

    class Meta:
        model = Enquiry
        fields = [
            "person",
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

    def validate_assigned_to(self, value: User | None) -> User | None:
        # Server-side enforcement of the assignable-operator rule — the API
        # must not trust the FE picker. Unassign (None) always allowed.
        if value is not None and not is_assignable_operator(value):
            raise serializers.ValidationError(NON_OPERATOR_ASSIGNEE_MSG)
        return value

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
