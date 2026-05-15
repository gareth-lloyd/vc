"""Viewsets for /quotations — CRUD + :send, :duplicate, :convert, :withdraw."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.api.permissions import IsReservationsWriter
from core.api.responses import not_implemented_response
from payments.enums import PaymentMethod
from reservations.enums import QuotationStatus
from reservations.filters import QuotationFilter
from reservations.models import Quotation, QuotationLine
from reservations.serializers import (
    BookingDetailSerializer,
    QuotationDetailSerializer,
    QuotationLineSerializer,
    QuotationLineWriteSerializer,
    QuotationListSerializer,
    QuotationWriteSerializer,
)
from reservations.services.bookings import BookingService


class QuotationViewSet(viewsets.ModelViewSet):
    """`/quotations` CRUD + colon-verb actions."""

    # Booking-synthesised quotations (`legacy_id` prefixed `booking-`) are
    # internal fixtures created by the data-migration loader so legacy bookings
    # can satisfy the QuotationLine PROTECT FK. They aren't real quotes and
    # must not surface in the public API.
    queryset = Quotation.objects.select_related("currency").exclude(
        legacy_id__startswith="booking-"
    )
    permission_classes = [IsAuthenticated, IsReservationsWriter]
    filterset_class = QuotationFilter
    ordering_fields = ["created_at", "updated_at", "status"]
    ordering = ["-created_at"]

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return QuotationListSerializer
        if self.action in ("create", "update", "partial_update"):
            return QuotationWriteSerializer
        return QuotationDetailSerializer

    @action(detail=True, methods=["post"], url_path="send")
    def send_quote(self, request: Request, pk: str | None = None) -> Response:
        """DRAFT → SENT."""
        quotation = self.get_object()
        quotation.send()
        return Response(QuotationDetailSerializer(quotation).data)

    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate(self, request: Request, pk: str | None = None) -> Response:
        """Clone header + lines into a new DRAFT quotation."""
        quotation = self.get_object()
        with transaction.atomic():
            clone = Quotation.objects.create(
                enquiry=quotation.enquiry,
                guest=quotation.guest,
                agent=quotation.agent,
                currency=quotation.currency,
                is_unbranded=quotation.is_unbranded,
                expires_at=quotation.expires_at,
                terms_version=quotation.terms_version,
            )
            for line in quotation.lines.all():
                QuotationLine.objects.create(
                    quotation=clone,
                    property=line.property,
                    date_from=line.date_from,
                    date_to=line.date_to,
                    adults=line.adults,
                    children=line.children,
                    pricing_snapshot=line.pricing_snapshot,
                    total=line.total,
                    is_selected=False,
                    is_manual=line.is_manual,
                    notes=line.notes,
                )
        return Response(
            QuotationDetailSerializer(clone).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="convert")
    def convert(self, request: Request, pk: str | None = None) -> Response:
        """Convert the selected line into a Booking.

        Body: `{"line": <id>, "payment_method"?: "card"|"bank_transfer"}`.
        """
        quotation = self.get_object()
        line_id = request.data.get("line")
        if line_id is None:
            return Response(
                {
                    "code": "validation_error",
                    "detail": "`line` is required",
                    "field_errors": {"line": ["This field is required."]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        line = get_object_or_404(QuotationLine, pk=line_id, quotation=quotation)
        # Accept the line (transitions quotation to ACCEPTED) before creating the booking.
        if quotation.status == QuotationStatus.SENT:
            quotation.accept(line)
        booking = BookingService.create_from_quotation_line(
            line,
            terms_version=quotation.terms_version,
            payment_method=request.data.get("payment_method", PaymentMethod.CARD.value),
            agent=quotation.agent,
            actor=request.user,
            allow_changeover_override=bool(request.data.get("allow_changeover_override", False)),
        )
        return Response(
            BookingDetailSerializer(booking).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="withdraw")
    def withdraw(self, request: Request, pk: str | None = None) -> Response:
        """Transition the quotation to CANCELLED (alias for cancel)."""
        quotation = self.get_object()
        reason = request.data.get("reason", "")
        quotation.cancel(reason=reason)
        return Response(QuotationDetailSerializer(quotation).data)

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request: Request, pk: str | None = None) -> Response:
        """PDF rendering — follow-up work."""
        return not_implemented_response("Quotation PDF rendering is not yet implemented.")


class QuotationLineViewSet(viewsets.ModelViewSet):
    """Nested `/quotations/{id}/lines` CRUD + :reorder."""

    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def get_queryset(self) -> Any:
        return (
            QuotationLine.objects.filter(quotation_id=self.kwargs["quotation_pk"])
            .exclude(legacy_id__startswith="booking-")
            .order_by("pk")
        )

    def get_serializer_class(self) -> type:
        if self.action in ("create", "update", "partial_update"):
            return QuotationLineWriteSerializer
        return QuotationLineSerializer

    def perform_create(self, serializer: Any) -> None:
        quotation = get_object_or_404(Quotation, pk=self.kwargs["quotation_pk"])
        serializer.save(quotation=quotation)

    @action(detail=False, methods=["post"], url_path="reorder")
    def reorder(self, request: Request, quotation_pk: str | None = None) -> Response:
        """Reorder by id list. Body: `{"ids": [int, ...]}`.

        QuotationLine has no `sort_order` column — reordering is a no-op
        beyond verifying the ids belong to the quotation, but we return the
        canonical order so the FE has confirmation.
        """
        ids = request.data.get("ids", [])
        if not isinstance(ids, list):
            return Response(
                {"code": "validation_error", "detail": "`ids` must be a list", "field_errors": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        lines = list(self.get_queryset().filter(pk__in=ids))
        return Response(QuotationLineSerializer(lines, many=True).data)
