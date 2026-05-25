"""Viewsets for /bookings — full state-machine surface."""

from __future__ import annotations

from datetime import date as date_type
from typing import Any

from django.db.models import Prefetch, QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import ContactEmail, ContactPhone
from core.api.permissions import IsReservationsWriter
from reservations.filters import BookingFilter
from reservations.models import Booking, BookingEvent, BookingNote
from reservations.serializers import (
    BookingDetailSerializer,
    BookingListSerializer,
    BookingNoteSerializer,
    BookingWriteSerializer,
)
from reservations.serializers.booking import BookingEventSerializer


def _parse_date(value: Any) -> date_type:
    """Parse `YYYY-MM-DD` strings into a `date` (DRF action payloads stay strings)."""
    if isinstance(value, date_type):
        return value
    return date_type.fromisoformat(str(value))


def _detail_owner_qs(qs: QuerySet[Booking]) -> QuerySet[Booking]:
    """Apply the FK/reverse chain BookingDetailSerializer's owner+commission walk.

    `Prefetch(..., to_attr=...)` populates a plain list on the parent, so the
    serializer can read it without re-issuing the `.filter(is_primary=True)`
    query that bypasses the prefetch cache.
    """
    return qs.select_related(
        "property__finance__contact",
        "property__group__finance",
    ).prefetch_related(
        Prefetch(
            "property__finance__contact__emails",
            queryset=ContactEmail.objects.filter(is_primary=True),
            to_attr="primary_emails",
        ),
        Prefetch(
            "property__finance__contact__phones",
            queryset=ContactPhone.objects.filter(is_primary=True),
            to_attr="primary_phones",
        ),
    )


class BookingViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """`/bookings` — no DELETE; lifecycle is action-driven."""

    permission_classes = [IsAuthenticated, IsReservationsWriter]
    filterset_class = BookingFilter
    ordering_fields = ["created_at", "updated_at", "date_from", "status"]
    ordering = ["-created_at"]

    def get_queryset(self) -> Any:
        qs = Booking.objects.filter(is_archived=False).select_related(
            "property",
            "guest",
            "agent",
            "assigned_to",
            "currency",
            "quotation_line",
        )
        # Every non-list action returns BookingDetailSerializer (`retrieve` and
        # the state-machine actions all route through `_refresh`), which walks
        # property -> finance -> contact -> emails/phones.
        if self.action != "list":
            qs = _detail_owner_qs(qs)
        return qs

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return BookingListSerializer
        if self.action in ("update", "partial_update"):
            return BookingWriteSerializer
        return BookingDetailSerializer

    # ------------------------------------------------------------------
    # State-machine action endpoints
    # ------------------------------------------------------------------
    def _refresh(self, booking: Booking) -> Response:
        # Re-fetch through the detail queryset so the owner/commission walk
        # hits the prefetch cache instead of issuing 5+ extra queries per
        # action response.
        fresh = _detail_owner_qs(Booking.objects.all()).get(pk=booking.pk)
        return Response(BookingDetailSerializer(fresh).data)

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request: Request, pk: str | None = None) -> Response:
        """Alias for :owner-approve when approval is required."""
        booking = self.get_object()
        booking.owner_approve(actor=request.user, reason=request.data.get("reason", ""))
        return self._refresh(booking)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        booking = self.get_object()
        reason = request.data.get("reason", "")
        booking.cancel(reason, actor=request.user)
        return self._refresh(booking)

    @action(detail=True, methods=["post"], url_path="owner-approve")
    def owner_approve(self, request: Request, pk: str | None = None) -> Response:
        booking = self.get_object()
        booking.owner_approve(actor=request.user, reason=request.data.get("reason", ""))
        return self._refresh(booking)

    @action(detail=True, methods=["post"], url_path="owner-decline")
    def owner_decline(self, request: Request, pk: str | None = None) -> Response:
        booking = self.get_object()
        reason = request.data.get("reason", "")
        booking.owner_decline(reason, actor=request.user)
        return self._refresh(booking)

    @action(detail=True, methods=["post"], url_path="modify-dates")
    def modify_dates(self, request: Request, pk: str | None = None) -> Response:
        booking = self.get_object()
        date_from = _parse_date(request.data["date_from"])
        date_to = _parse_date(request.data["date_to"])
        reason = request.data.get("reason", "")
        booking.modify_dates(date_from, date_to, actor=request.user, reason=reason)
        return self._refresh(booking)

    @action(detail=True, methods=["post"], url_path="modify-guests")
    def modify_guests(self, request: Request, pk: str | None = None) -> Response:
        booking = self.get_object()
        adults = int(request.data["adults"])
        children = int(request.data.get("children", 0))
        reason = request.data.get("reason", "")
        booking.modify_guests(adults, children, actor=request.user, reason=reason)
        return self._refresh(booking)

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request: Request, pk: str | None = None) -> Response:
        booking = self.get_object()
        booking.archive(actor=request.user)
        return self._refresh(booking)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request: Request, pk: str | None = None) -> Response:
        # Restore needs to be reachable on archived rows — bypass the default
        # `is_archived=False` filter while keeping the owner prefetches.
        booking = get_object_or_404(_detail_owner_qs(Booking.objects.all()), pk=pk)
        booking.restore(actor=request.user)
        return self._refresh(booking)

    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request: Request, pk: str | None = None) -> Response:
        booking = self.get_object()
        booking.check_in(actor=request.user)
        return self._refresh(booking)

    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out(self, request: Request, pk: str | None = None) -> Response:
        booking = self.get_object()
        booking.check_out(actor=request.user)
        return self._refresh(booking)

    @action(detail=True, methods=["post"], url_path="resend-confirmation")
    def resend_confirmation(self, request: Request, pk: str | None = None) -> Response:
        booking = self.get_object()
        booking.send_confirmation_email(actor=request.user)
        return self._refresh(booking)

    @action(detail=True, methods=["get"], url_path="activity")
    def activity(self, request: Request, pk: str | None = None) -> Response:
        """BookingEvent timeline."""
        booking = self.get_object()
        events = BookingEvent.objects.filter(booking=booking).order_by("created_at")
        return Response(BookingEventSerializer(events, many=True).data)


class BookingArchiveViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only surface for archived bookings."""

    permission_classes = [IsAuthenticated, IsReservationsWriter]
    filterset_class = BookingFilter
    ordering_fields = ["created_at", "archived_at", "date_from"]
    ordering = ["-archived_at"]

    def get_queryset(self) -> Any:
        qs = Booking.objects.filter(is_archived=True).select_related(
            "property",
            "guest",
            "agent",
            "assigned_to",
            "currency",
            "quotation_line",
        )
        if self.action != "list":
            qs = _detail_owner_qs(qs)
        return qs

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return BookingListSerializer
        return BookingDetailSerializer


class BookingNoteViewSet(viewsets.ModelViewSet):
    """Nested `/bookings/{id}/notes` CRUD."""

    serializer_class = BookingNoteSerializer
    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def get_queryset(self) -> Any:
        return BookingNote.objects.filter(booking_id=self.kwargs["booking_pk"]).order_by(
            "created_at"
        )

    def perform_create(self, serializer: Any) -> None:
        booking = get_object_or_404(Booking, pk=self.kwargs["booking_pk"])
        serializer.save(booking=booking, author=self.request.user)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
