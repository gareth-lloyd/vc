"""Owner-portal booking-backed endpoints.

These live in `reservations` (not `owners`) because they read
`reservations.Booking`: the import spine runs reservations → owners, so a
reservations view may import `owners.scoping` / `owners.permissions` downward,
but `owners` may not reach up to Booking. Property/identity-only owner views
stay in the `owners` app.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from owners.permissions import IsOwner
from owners.scoping import (
    BLOCK_WRITER_ROLES,
    BOOKING_APPROVER_ROLES,
    owner_property_ids,
    owner_property_ids_for_roles,
    owner_visibility_map,
)
from properties.models import Property
from reservations.enums import BookingStatus
from reservations.models import Booking, OwnerBlock
from reservations.serializers._contact_reads import contact_name
from reservations.serializers.owner import (
    OwnerBlockSerializer,
    OwnerBlockWriteSerializer,
    OwnerBookingDetailSerializer,
    OwnerBookingListSerializer,
)
from reservations.services.availability import AvailabilityService
from reservations.services.charges import with_charges_total
from reservations.services.owner_block import OwnerBlockService
from reservations.services.owner_finance import owner_money_for_booking

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.db.models import QuerySet
    from rest_framework.request import Request

    from accounts.models import User

# Excluded from owner KPIs: drafts never confirmed and the dead-end states.
# CHECKED_OUT is kept — a completed stay is real revenue.
_NON_COUNTING_STATUSES = (
    BookingStatus.DRAFT.value,
    BookingStatus.CANCELLED.value,
    BookingStatus.EXPIRED.value,
    BookingStatus.DECLINED.value,
)
_UPCOMING_WINDOW_DAYS = 30
_UPCOMING_LIMIT = 5


class OwnerDashboardView(APIView):
    """`GET /owner/dashboard` — cheap KPI aggregates over the scoped bookings.

    Money figures ("your share" net) render only for properties the caller's
    org has a `view_full_money` grant on; with no such grant the net is null.
    Deferred KPIs (next payout, utilisation %) are intentionally omitted.
    """

    permission_classes = [IsOwner]

    def get(self, request: Request) -> Response:
        user = cast("User", request.user)
        property_ids = owner_property_ids(user)
        visibility = owner_visibility_map(user)
        today = timezone.localdate()
        year_start = date(today.year, 1, 1)

        scoped = Booking.objects.filter(property_id__in=property_ids).exclude(
            status__in=_NON_COUNTING_STATUSES
        )
        ytd = scoped.filter(date_from__gte=year_start, date_from__lte=today)
        # Booking count is operational, not financial — always shown.
        bookings_count = ytd.count()

        # Both money KPIs are gated to view_full_money properties: gross revenue
        # is as sensitive as the per-booking rental_price the booking endpoint
        # redacts (for a single booking the sum *is* that price). With no
        # full-money grant, both stay null rather than leaking via aggregation.
        full_money_ids = {pid for pid, flags in visibility.items() if flags["view_full_money"]}
        gross: Decimal | None = None
        net_to_owner: Decimal | None = None
        if full_money_ids:
            money_ytd = ytd.filter(property_id__in=full_money_ids)
            gross = money_ytd.aggregate(total=Sum("rental_price"))["total"] or Decimal("0")
            net_to_owner = Decimal("0")
            # Per-booking, not values_list of snapshots: manual charge items
            # live outside the snapshot, and their owner effect needs the
            # charges annotation + the property's commission config. Gross
            # stays rental-price-based — charges are extras, not rent.
            money_bookings = with_charges_total(money_ytd).select_related("property__finance")
            for money_booking in money_bookings:
                money = owner_money_for_booking(money_booking)
                if money is not None:
                    net_to_owner += money["net_to_owner"]

        by_status = {
            row["status"]: row["count"]
            for row in Property.objects.filter(id__in=property_ids)
            .values("status")
            .annotate(count=Count("id"))
        }

        upcoming = (
            scoped.filter(
                date_from__gte=today,
                date_from__lte=today + timedelta(days=_UPCOMING_WINDOW_DAYS),
            )
            .select_related("property", "person")
            .order_by("date_from")[:_UPCOMING_LIMIT]
        )
        upcoming_payload = [
            {
                "reference": booking.reference,
                "property_id": booking.property_id,
                "property_name": booking.property.name if booking.property_id else None,
                "date_from": booking.date_from,
                "date_to": booking.date_to,
                # Named, contact withheld — the owner redaction policy.
                "guest_name": contact_name(booking.person if booking.person_id else None),
                "adults": booking.adults,
                "children": booking.children,
            }
            for booking in upcoming
        ]

        return Response(
            {
                "ytd": {
                    "bookings": bookings_count,
                    "gross_revenue": f"{gross:.2f}" if gross is not None else None,
                    "net_to_owner": f"{net_to_owner:.2f}" if net_to_owner is not None else None,
                },
                "properties": {"total": len(property_ids), "by_status": by_status},
                "upcoming_arrivals": upcoming_payload,
            }
        )


class OwnerBookingViewSet(viewsets.ReadOnlyModelViewSet):
    """`GET /owner/bookings` (+ `/{id}`) — scoped, redacted booking reads.

    Server-side scoping restricts to the caller's granted properties, so a
    retrieve of any other booking 404s. Field-level redaction lives in the
    serializer, keyed off the per-property visibility map placed in context.
    DRAFT and archived bookings are hidden; cancellations stay visible as
    history.
    """

    permission_classes = [IsOwner]

    def get_serializer_class(self) -> type[serializers.BaseSerializer]:
        if self.action == "retrieve":
            return OwnerBookingDetailSerializer
        return OwnerBookingListSerializer

    def get_queryset(self) -> QuerySet[Booking]:
        user = cast("User", self.request.user)
        property_ids = owner_property_ids(user)
        # "Repeat guest" = this customer has another booking at the caller's own
        # villas — a single correlated EXISTS, constant-query regardless of rows.
        # GAP-045 3d-C: keyed on `person_id` (NOT NULL since 3d-A) now that the
        # production writers no longer persist the nullable `guest` leg — a
        # `guest_id=OuterRef("guest_id")` join would be NULL=NULL → never a match.
        repeat = Exists(
            Booking.objects.filter(
                person_id=OuterRef("person_id"), property_id__in=property_ids
            ).exclude(pk=OuterRef("pk"))
        )
        return (
            Booking.objects.filter(property_id__in=property_ids, is_archived=False)
            .exclude(status=BookingStatus.DRAFT.value)
            .select_related(
                "property",
                "person",
                "person__country",
                "currency",
            )
            .prefetch_related("person__emails", "person__phones")
            .annotate(is_repeat_guest=repeat)
            .order_by("-date_from")
        )

    def get_serializer_context(self) -> dict[str, Any]:
        user = cast("User", self.request.user)
        context = super().get_serializer_context()
        context["visibility"] = owner_visibility_map(user)
        context["approver_property_ids"] = owner_property_ids_for_roles(
            user, BOOKING_APPROVER_ROLES
        )
        return context

    def _approvable_booking(self, request: Request, pk: str | None) -> Booking:
        """Fetch a booking the caller may *approve* (else 403/404).

        `get_object` already 404s on a villa the caller can't read; this adds
        the role floor: a readable booking on a villa the caller lacks an
        approver role on → 403.
        """
        booking = self.get_object()
        user = cast("User", request.user)
        if booking.property_id not in owner_property_ids_for_roles(user, BOOKING_APPROVER_ROLES):
            raise PermissionDenied("You do not have approval rights for this property.")
        return booking

    def _approval_response(self, booking: Booking) -> Response:
        serializer = OwnerBookingDetailSerializer(booking, context=self.get_serializer_context())
        return Response(serializer.data)

    # The entry path into PENDING_OWNER_APPROVAL already exists:
    # `BookingService.create_from_quotation_line` calls `booking.submit()` (vs
    # `auto_accept()`) when the property's effective `bookings_require_pre_approval`
    # setting is true. So these endpoints have real production inputs for any
    # pre-approval villa — no extra trigger needed. (The mixed/chaos seed profiles
    # mark some villas pre-approval, so dev data exercises this path too.)
    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request: Request, pk: str | None = None) -> Response:
        """PENDING_OWNER_APPROVAL → AWAITING_DEPOSIT (fires lifecycle comms)."""
        booking = self._approvable_booking(request, pk)
        # Wrap the transition: it fires `booking_transitioned`, which the
        # payments app consumes to schedule the booking's payments. The signal
        # dispatch runs after `_transition`'s own atomic block commits, so
        # without this outer transaction a scheduling failure would leave the
        # booking committed in AWAITING_DEPOSIT with no payment rows (and wedge
        # a retry on InvalidTransition). The atomic ties status + payments into
        # one indivisible unit — the same guarantee the quotation-convert path
        # gets from its own `transaction.atomic` (see views/quotation.py).
        with transaction.atomic():
            booking.owner_approve(actor=request.user, reason=request.data.get("reason", ""))
        return self._approval_response(booking)

    @action(detail=True, methods=["post"], url_path="decline")
    def decline(self, request: Request, pk: str | None = None) -> Response:
        """PENDING_OWNER_APPROVAL → DECLINED. Requires a non-empty reason."""
        booking = self._approvable_booking(request, pk)
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise serializers.ValidationError({"reason": "A decline reason is required."})
        booking.owner_decline(reason, actor=request.user)
        return self._approval_response(booking)


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _owner_segment(segment: Any) -> dict[str, Any]:
    # Only the public availability category — never the internal block id.
    return {"available": segment.available, "reason": segment.reason}


class OwnerPropertyCalendarView(APIView):
    """`GET /owner/properties/{id}/calendar` — read-only availability.

    Reuses `AvailabilityService.calendar` behind a scope gate: an ungranted
    villa 404s. Cells expose only the availability category (booked / hold
    kind / available) and changeover segments — never guest identity, and not
    the internal hold `block_id` (owners can't act on holds).
    """

    permission_classes = [IsOwner]

    def get(self, request: Request, property_id: int) -> Response:
        user = cast("User", request.user)
        property_obj = get_object_or_404(
            Property.objects.filter(id__in=owner_property_ids(user)), pk=property_id
        )
        range_start = _parse_iso_date(request.query_params.get("from"))
        range_end = _parse_iso_date(request.query_params.get("to"))
        if range_start is None or range_end is None:
            return Response(
                {
                    "code": "validation_error",
                    "detail": "`from` and `to` query params are required (YYYY-MM-DD)",
                    "field_errors": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        cells = AvailabilityService.calendar(property_obj, range_start, range_end)
        payload = []
        for day, cell in sorted(cells.items()):
            entry: dict[str, Any] = {
                "date": day.isoformat(),
                "available": cell.available,
                "reason": cell.reason,
            }
            if cell.segments is not None:
                entry["segments"] = {
                    "am": _owner_segment(cell.segments["am"]),
                    "pm": _owner_segment(cell.segments["pm"]),
                }
            payload.append(entry)
        # `can_request_block` gates the "Request block" affordance without a
        # second round-trip — sourced from the role-scoped writable set, not the
        # broader readable set this view already filtered on.
        can_request_block = property_obj.pk in owner_property_ids_for_roles(
            user, BLOCK_WRITER_ROLES
        )
        return Response(
            {
                "property_id": property_obj.pk,
                "can_request_block": can_request_block,
                "cells": payload,
            }
        )


def _resolve_writable_property(user: User, property_id: int, roles: Sequence[str]) -> Property:
    """Resolve a property the caller may *write*, else 403 (readable) / 404.

    Distinguishing 403 from 404 mirrors the read endpoints: a villa the caller
    can see but not write returns 403; one they can't see at all 404s rather
    than leaking its existence.
    """
    if property_id in owner_property_ids_for_roles(user, roles):
        return get_object_or_404(Property, pk=property_id)
    if property_id in owner_property_ids(user):
        raise PermissionDenied("You do not have write access to this property.")
    raise Http404


class OwnerBlockViewSet(viewsets.GenericViewSet):
    """`/owner/block-requests` — owner-submitted availability block requests.

    List/create the caller's own requests; cancel one they raised. Property
    write-scope is enforced against `BLOCK_WRITER_ROLES` (VIEW_ONLY → 403).
    """

    permission_classes = [IsOwner]

    def get_queryset(self) -> QuerySet[OwnerBlock]:
        user = cast("User", self.request.user)
        return (
            OwnerBlock.objects.filter(created_by=user)
            .select_related("property")
            .order_by("-created_at")
        )

    def list(self, request: Request) -> Response:
        qs = self.get_queryset()
        property_id = request.query_params.get("property")
        if property_id:
            qs = qs.filter(property_id=property_id)
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(OwnerBlockSerializer(qs, many=True).data)

    def create(self, request: Request) -> Response:
        user = cast("User", request.user)
        serializer = OwnerBlockWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        property_obj = _resolve_writable_property(user, data["property"], BLOCK_WRITER_ROLES)
        block_request = OwnerBlockService.create(
            property=property_obj,
            created_by=user,
            date_from=data["date_from"],
            date_to=data["date_to"],
            kind=data["kind"],
            notes=data["notes"],
        )
        return Response(
            OwnerBlockSerializer(block_request).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        user = cast("User", request.user)
        block_request = get_object_or_404(OwnerBlock, pk=pk, created_by=user)
        OwnerBlockService.cancel(block_request, actor=user)
        return Response(OwnerBlockSerializer(block_request).data)
