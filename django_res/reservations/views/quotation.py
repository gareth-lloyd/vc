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
from reservations.services.quotation_render import (
    build_quotation_context,
    render_quotation_html,
)
from reservations.services.quotation_transmission import (
    SEND_PATH_MANUAL,
    record_quote_sent,
)
from reservations.services.quotations import QuotationService
from reservations.views.status_counts import StatusCountsMixin


class QuotationViewSet(StatusCountsMixin, viewsets.ModelViewSet):
    """`/quotations` CRUD + colon-verb actions."""

    # Booking-synthesised quotations (`legacy_id` prefixed `booking-`) are
    # internal fixtures created by the data-migration loader so legacy bookings
    # can satisfy the QuotationLine PROTECT FK. They aren't real quotes and
    # must not surface in the public API.
    queryset = (
        Quotation.objects.select_related(
            "currency",
            "guest",
            "enquiry",
            "agent",
        )
        # The detail serializer nests `lines`, each of which derives a
        # hero_image_url from its property's images — prefetch the whole
        # walk so a quotation with N lines stays at a constant query count.
        .prefetch_related("lines__property__images")
        .exclude(legacy_id__startswith="booking-")
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

    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request: Request, pk: str | None = None) -> Response:
        """Render the quote HTML + the copy an operator can edit.

        Optional `subject`/`intro`/`signoff` query params are operator copy
        overrides; threading them through means the preview the operator sees
        reflects their in-flight edits and is byte-for-byte what `:send` will
        dispatch with the same overrides. Omitting them previews the defaults.
        """
        quotation = self.get_object()
        overrides = {
            key: request.query_params[key]
            for key in ("subject", "intro", "signoff")
            if key in request.query_params
        }
        context = build_quotation_context(quotation, **overrides)
        return Response(
            {
                "html": render_quotation_html(quotation, **overrides),
                "subject": context["subject"],
                "intro": context["intro"],
                "signoff": context["signoff"],
            }
        )

    @action(detail=True, methods=["post"], url_path="send")
    def send_quote(self, request: Request, pk: str | None = None) -> Response:
        """DRAFT → SENT via the in-app SMTP path.

        Optional `subject`/`intro`/`signoff` in the body are operator copy
        overrides; omitting them sends the centralised defaults.
        """
        quotation = self.get_object()
        quotation.send(
            actor=request.user,
            subject=request.data.get("subject"),
            intro=request.data.get("intro"),
            signoff=request.data.get("signoff"),
        )
        return Response(QuotationDetailSerializer(quotation).data)

    @action(detail=True, methods=["post"], url_path="mark-manually-sent")
    def mark_manually_sent(self, request: Request, pk: str | None = None) -> Response:
        """Mark a quote as sent outside the system (operator copy-pasted into Outlook).

        Same downstream state writes as `:send` (status flip, Enquiry → QUOTED,
        Zoho push queued, EnquiryEvent with `send_path="manual"`) but does NOT
        dispatch an email — Res didn't actually send the mail, so no `EmailLog`
        row is created. Idempotent: re-POST on an already-SENT quotation returns
        200 with no extra side effects.
        """
        quotation = self.get_object()
        record_quote_sent(quotation, send_path=SEND_PATH_MANUAL, actor=request.user)
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
                    discount=line.discount,
                    inclusions=line.inclusions,
                    is_selected=False,
                    is_manual=line.is_manual,
                    price_override_reason=line.price_override_reason,
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
        # Accept + create must share a transaction so an `OverlappingBooking`
        # raised by the booking service rolls back the quotation acceptance,
        # otherwise the quotation gets stuck in ACCEPTED with no booking row.
        with transaction.atomic():
            if quotation.status == QuotationStatus.SENT:
                quotation.accept(line, actor=request.user)
            booking = BookingService.create_from_quotation_line(
                line,
                terms_version=quotation.terms_version,
                payment_method=request.data.get("payment_method", PaymentMethod.CARD.value),
                agent=quotation.agent,
                actor=request.user,
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
            .select_related("property")
            # The read serializer derives hero_image_url per line — prefetch
            # the property's images so a list of N lines stays constant-query.
            .prefetch_related("property__images")
            .order_by("pk")
        )

    def get_serializer_class(self) -> type:
        if self.action in ("create", "update", "partial_update"):
            return QuotationLineWriteSerializer
        return QuotationLineSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # The write serializer doesn't carry total/pricing_snapshot — echo the
        # freshly-priced line back through the read serializer so the FE sees
        # the server-computed values without a follow-up GET.
        read = QuotationLineSerializer(serializer.instance)
        return Response(read.data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        read = QuotationLineSerializer(serializer.instance)
        return Response(read.data)

    def perform_create(self, serializer: Any) -> None:
        quotation = get_object_or_404(Quotation, pk=self.kwargs["quotation_pk"])
        line = serializer.save(quotation=quotation)
        self._reprice(line)

    def perform_update(self, serializer: Any) -> None:
        # Persist the edited fields (adults, discount, …) BEFORE repricing so
        # `_reprice` re-reads them off the row. Without the save the patched
        # values would never reach the DB and the engine would price the stale
        # row.
        line = serializer.save()
        self._reprice(line)

    def _reprice(self, line: QuotationLine) -> None:
        """Recompute a non-manual line's total + pricing_snapshot.

        Manual-override lines (`is_manual=True`) keep whatever total /
        pricing_snapshot the operator supplied — the manual-override write
        surface is a later phase, so for now a manual line is simply left
        untouched here.

        Per FG-006 we re-read the row under `select_for_update` inside a
        transaction before repricing, so a concurrent write to the same line
        serialises behind this update rather than racing it.
        """
        if line.is_manual:
            return
        with transaction.atomic():
            locked = (
                QuotationLine.objects.select_for_update()
                .select_related("property", "quotation__currency")
                .get(pk=line.pk)
            )
            QuotationService.price_line(locked.quotation, locked)
        # Reflect the persisted price back onto the serializer's instance so
        # the response (built from it) carries the server-computed values —
        # including any changeover-shifted dates (GAP-007).
        line.total = locked.total
        line.pricing_snapshot = locked.pricing_snapshot
        line.date_from = locked.date_from
        line.date_to = locked.date_to

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
