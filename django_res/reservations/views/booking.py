"""Viewsets for /bookings — full state-machine surface."""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import (
    DecimalField,
    Prefetch,
    Q,
    QuerySet,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import PersonEmail, PersonPhone
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
from reservations.services.charges import with_charges_total as _with_charges_total
from reservations.views.status_counts import StatusCountsMixin


def _parse_date(value: Any) -> date_type:
    """Parse `YYYY-MM-DD` strings into a `date` (DRF action payloads stay strings)."""
    if isinstance(value, date_type):
        return value
    return date_type.fromisoformat(str(value))


def _with_amount_paid(qs: QuerySet[Booking]) -> QuerySet[Booking]:
    """Annotate the settled rental sum BookingListSerializer.amount_paid reads.

    Keeps list responses single-query; un-annotated instances fall back to a
    per-row aggregate in the serializer. Statuses/purposes are string literals
    because `reservations` must not import `payments` (import spine).
    """
    return qs.annotate(
        # Coalesce so a payment-less booking annotates as 0, not NULL — a None
        # would look "un-annotated" to the serializer and trip its per-row
        # fallback aggregate (an N+1).
        amount_paid_total=Coalesce(
            Sum(
                "payments__amount",
                filter=Q(
                    payments__status="succeeded",
                    payments__purpose__in=("deposit", "balance"),
                ),
            ),
            Value(Decimal("0")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )


def _detail_owner_qs(qs: QuerySet[Booking]) -> QuerySet[Booking]:
    """Apply the FK/reverse chain BookingDetailSerializer's owner+commission walk.

    `Prefetch(..., to_attr=...)` populates a plain list on the parent, so the
    serializer can read it without re-issuing the `.filter(is_primary=True)`
    query that bypasses the prefetch cache.
    """
    return qs.select_related(
        # GAP-045 Unit 3d-3: the detail serializer resolves guest name + email
        # solely from the Person mirror, so join it + prefetch its email on every
        # detail/action path that funnels through here.
        "person",
        # GAP-046: the owner block surfaces the contact's agency name (the
        # successor to free-text `company`), so deepen the join to its agency.
        "property__finance__contact__agency",
        "property__settings",
    ).prefetch_related(
        "person__emails",
        # GAP-077: `payment_splits` walks the schedule rows in Python, so a
        # plain prefetch satisfies it (see `payment_component_splits`).
        "payments",
        Prefetch(
            "property__finance__contact__emails",
            queryset=PersonEmail.objects.filter(is_primary=True),
            to_attr="primary_emails",
        ),
        Prefetch(
            "property__finance__contact__phones",
            queryset=PersonPhone.objects.filter(is_primary=True),
            to_attr="primary_phones",
        ),
    )


class BookingViewSet(
    StatusCountsMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """`/bookings` — no DELETE, no POST; lifecycle is action-driven.

    Bookings are created via `POST /quotations/{id}:convert` only, so every
    one passes through `BookingService.create_from_quotation_line` (LEAD
    guest, server-priced money, payment schedule, hold release, audit).
    Direct creation returns when GAP-020's `create_direct` lands — routed
    through the service, never a bare serializer save.
    """

    permission_classes = [IsAuthenticated, IsReservationsWriter]
    filterset_class = BookingFilter
    ordering_fields = ["created_at", "updated_at", "date_from", "status"]
    ordering = ["-created_at"]

    def get_queryset(self) -> Any:
        qs: QuerySet[Booking] = Booking.objects.filter(is_archived=False).select_related(
            "property",
            # GAP-045 Unit 3d-3: name + email resolve solely from the Person
            # mirror. Join it; the email prefetch is path-specific below.
            "person",
            "agent",
            "assigned_to",
            "currency",
            "quotation_line",
        )
        # Annotate only the actions whose response serializer reads
        # `amount_paid`. The Sum's LEFT JOIN onto payments must not leak into
        # `status_counts` (its Count('id') would count booking x payment rows)
        # or the mutation actions (their responses re-fetch via `_refresh`,
        # which annotates separately).
        if self.action in ("list", "retrieve"):
            qs = _with_charges_total(_with_amount_paid(qs))
        # Every non-list action returns BookingDetailSerializer (`retrieve` and
        # the state-machine actions all route through `_refresh`), which walks
        # property -> finance -> contact -> emails/phones AND person -> emails
        # (both prefetched by `_detail_owner_qs`). The list path prefetches the
        # person email on its own so the two never double up on one queryset.
        if self.action == "list":
            qs = qs.prefetch_related("person__emails")
        else:
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
        fresh = _detail_owner_qs(_with_charges_total(_with_amount_paid(Booking.objects.all()))).get(
            pk=booking.pk
        )
        return Response(BookingDetailSerializer(fresh).data)

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request: Request, pk: str | None = None) -> Response:
        """Alias for :owner-approve when approval is required."""
        booking = self.get_object()
        # Atomic so the AWAITING_DEPOSIT transition and the payment rows the
        # booking_transitioned receiver schedules commit (or roll back) as one
        # unit — the contract documented on
        # payments.signals._schedule_payments_on_booking_confirmed.
        with transaction.atomic():
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
        # Same atomicity contract as :confirm above.
        with transaction.atomic():
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
        qs: QuerySet[Booking] = Booking.objects.filter(is_archived=True).select_related(
            "property",
            "person",
            "agent",
            "assigned_to",
            "currency",
            "quotation_line",
        )
        qs = _with_charges_total(_with_amount_paid(qs))
        if self.action == "list":
            qs = qs.prefetch_related("person__emails")
        else:
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
