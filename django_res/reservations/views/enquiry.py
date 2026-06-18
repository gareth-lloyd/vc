"""Viewsets for /enquiries — CRUD plus :assign, :convert, :close, :reopen."""

from __future__ import annotations

from typing import Any

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import User
from core.api.permissions import IsReservationsWriter
from reservations.enums import EnquiryLostReason, EnquiryStatus, LeadStatus
from reservations.filters import EnquiryFilter
from reservations.models import BookingHold, Enquiry, EnquiryEvent, EnquiryNote, Quotation
from reservations.serializers import (
    EnquiryDetailSerializer,
    EnquiryEventSerializer,
    EnquiryListSerializer,
    EnquiryNoteSerializer,
    EnquiryWriteSerializer,
)
from reservations.views.status_counts import StatusCountsMixin


def _quotations_prefetch() -> Prefetch:
    """The quote-stack prefetch the detail serializer walks (`.quotations.lines`).

    Reach `lines__property__images` so each line's `property_name` /
    `hero_image_url` resolves from the prefetch cache — `hero_image_url()` walks
    `property.images` in Python, so without it every line fires a property +
    images lookup (the same N+1 guard `QuotationViewSet` keeps). Same deal for
    each line's `hold` field: it must serialise from the `live_holds` to_attr,
    never a per-line fallback query."""
    return Prefetch(
        "quotations",
        queryset=Quotation.objects.real()
        .select_related("guest", "agent", "enquiry")
        .prefetch_related(
            "lines__property__images",
            "lines__currency",
            Prefetch(
                "lines__holds",
                queryset=BookingHold.objects.filter(released_at__isnull=True),
                to_attr="live_holds",
            ),
        ),
    )


def _detail_queryset() -> Any:
    """Enquiry queryset shaped for the detail serializer — FKs joined and the
    quote-stack prefetched so `EnquiryDetailSerializer` walks `.quotations.lines`
    without an N+1."""
    return Enquiry.objects.select_related(
        "guest", "property", "region", "agent", "assigned_to"
    ).prefetch_related(_quotations_prefetch())


class EnquiryViewSet(StatusCountsMixin, viewsets.ModelViewSet):
    """`/enquiries` CRUD plus colon-verb action endpoints."""

    queryset = Enquiry.objects.select_related("guest", "property", "region", "agent", "assigned_to")
    permission_classes = [IsAuthenticated, IsReservationsWriter]
    filterset_class = EnquiryFilter
    ordering_fields = ["created_at", "updated_at", "status"]
    ordering = ["-created_at"]

    def get_queryset(self) -> Any:
        qs = super().get_queryset()
        # Detail (and detail-shaped action) responses inline the quote-stack
        # for the grouped-list UI; list stays slim, so prefetch only when the
        # detail serializer is actually going to walk `.quotations.lines`.
        if self.action not in ("list",) and self.action not in (
            "create",
            "update",
            "partial_update",
        ):
            qs = qs.prefetch_related(_quotations_prefetch())
        return qs

    def get_serializer_class(self) -> type:
        if self.action in ("list",):
            return EnquiryListSerializer
        if self.action in ("create", "update", "partial_update"):
            return EnquiryWriteSerializer
        return EnquiryDetailSerializer

    def _detail_response(
        self, enquiry: Enquiry, status_code: int, headers: dict[str, str] | None = None
    ) -> Response:
        """Re-serialise a written enquiry in detail shape.

        Writes validate with `EnquiryWriteSerializer`, but the response must
        carry the server-assigned `id`/`reference`/`status` and computed fields
        the SPA parses — so re-fetch through the prefetched detail queryset and
        serialise with `EnquiryDetailSerializer`. Mirrors `BookingViewSet._refresh`.
        """
        fresh = _detail_queryset().get(pk=enquiry.pk)
        serializer = EnquiryDetailSerializer(fresh, context=self.get_serializer_context())
        return Response(serializer.data, status=status_code, headers=headers)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        write = self.get_serializer(data=request.data)
        write.is_valid(raise_exception=True)
        self.perform_create(write)
        headers = self.get_success_headers(write.data)
        enquiry = write.instance
        assert enquiry is not None  # populated by save()
        return self._detail_response(enquiry, status.HTTP_201_CREATED, headers)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        write = self.get_serializer(instance, data=request.data, partial=partial)
        write.is_valid(raise_exception=True)
        self.perform_update(write)
        enquiry = write.instance
        assert enquiry is not None  # populated by save()
        return self._detail_response(enquiry, status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # Action endpoints
    # ------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request: Request, pk: str | None = None) -> Response:
        """Assign (or unassign) an operator. Body: `{"user": <id> | null}`."""
        enquiry = self.get_object()
        user_id = request.data.get("user")
        user: User | None = None
        if user_id is not None:
            user = get_object_or_404(User, pk=user_id)
        enquiry.assign(user, actor=request.user)
        return Response(EnquiryDetailSerializer(enquiry).data)

    @action(detail=True, methods=["post"], url_path="convert")
    def convert(self, request: Request, pk: str | None = None) -> Response:
        """Convert this enquiry — body: `{"quotation": <id>}`.

        Idempotent: a second :convert on an already-CONVERTED enquiry
        returns the current state. The auto-conversion path (a Quotation
        being accepted flips its parent enquiry inline) means an
        operator's explicit convert call can race the implicit one;
        treating the second hit as an error would expose the race to the
        UI as a 409.
        """
        enquiry = self.get_object()
        if enquiry.status == EnquiryStatus.CONVERTED.value:
            return self._detail_response(enquiry, status.HTTP_200_OK)
        quotation_id = request.data.get("quotation")
        # Scoped to *this* enquiry's quotations — citing another enquiry's
        # quote would mark this one converted with an audit pointer at an
        # unrelated quotation.
        quotation = get_object_or_404(Quotation, pk=quotation_id, enquiry=enquiry)
        enquiry.convert(quotation, actor=request.user)
        # Re-fetch through the prefetched detail queryset: convert() runs
        # refresh_locked(), which wipes this instance's prefetch cache, so a bare
        # serialization would re-query `quotations` through the *default* manager
        # (an N+1 and, for the now-CONVERTED status, an unscoped read that drops
        # the `.real()` synthetic-quote filter the `quotes_to_convert` metric and
        # quote-stack rely on). `_detail_response` re-fetches with the `.real()`
        # prefetch intact.
        return self._detail_response(enquiry, status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request: Request, pk: str | None = None) -> Response:
        """Mark closed-dead. Body: `{"reason": "...", "lost_reason": "..."}`.

        `reason` is the free-text note; `lost_reason` is an optional structured
        `EnquiryLostReason` (defaults to UNKNOWN). An unknown structured value
        is rejected rather than silently coerced.
        """
        enquiry = self.get_object()
        reason = request.data.get("reason", "")
        lost_reason = request.data.get("lost_reason") or EnquiryLostReason.UNKNOWN.value
        if lost_reason not in EnquiryLostReason.values:
            return Response(
                {"lost_reason": [f"'{lost_reason}' is not a valid lost reason."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        enquiry.lose(reason=reason, lost_reason=lost_reason, actor=request.user)
        return Response(EnquiryDetailSerializer(enquiry).data)

    @action(detail=True, methods=["post"], url_path="set-lead-status")
    def set_lead_status(self, request: Request, pk: str | None = None) -> Response:
        """Set the lead temperature. Body: `{"lead_status": "hot|warm|cold|dead"}`.

        Audited via the model's `set_lead_status` (writes a LEAD_STATUS_CHANGED
        event; a no-op when unchanged). An unknown value is rejected with 400
        rather than surfaced as the model's bare `ValueError` (a 500); validating
        here also guarantees no mutation on a bad value. Returns the detail shape
        (re-fetched through the prefetched queryset, mirroring `:close`).
        """
        enquiry = self.get_object()
        lead_status = request.data.get("lead_status")
        if lead_status not in LeadStatus.values:
            return Response(
                {"lead_status": [f"'{lead_status}' is not a valid lead status."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        enquiry.set_lead_status(lead_status, actor=request.user)
        return self._detail_response(enquiry, status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="reopen")
    def reopen(self, request: Request, pk: str | None = None) -> Response:
        """Reopen a LOST enquiry."""
        enquiry = self.get_object()
        reason = request.data.get("reason", "")
        enquiry.reopen(actor=request.user, reason=reason)
        return Response(EnquiryDetailSerializer(enquiry).data)

    @action(detail=True, methods=["get"], url_path="activity")
    def activity(self, request: Request, pk: str | None = None) -> Response:
        """Read-only activity timeline."""
        enquiry = self.get_object()
        events = EnquiryEvent.objects.filter(enquiry=enquiry).order_by("created_at")
        return Response(EnquiryEventSerializer(events, many=True).data)


class EnquiryNoteViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Nested `/enquiries/{id}/notes` — list + create."""

    serializer_class = EnquiryNoteSerializer
    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def get_queryset(self) -> Any:
        return EnquiryNote.objects.filter(enquiry_id=self.kwargs["enquiry_pk"]).order_by(
            "created_at"
        )

    def perform_create(self, serializer: Any) -> None:
        enquiry = get_object_or_404(Enquiry, pk=self.kwargs["enquiry_pk"])
        serializer.save(enquiry=enquiry, author=self.request.user)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
