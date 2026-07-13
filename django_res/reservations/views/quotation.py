"""Viewsets for /quotations — CRUD + :send, :duplicate, :convert, :withdraw."""

from __future__ import annotations

from typing import Any

import structlog
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.api.permissions import IsReservationsWriter
from core.exceptions import InvalidTransition, QuotationLocked, TermsNotAccepted
from core.idempotency import integrity_conflict_guard
from reservations.enums import PaymentMethod, QuotationStatus
from reservations.filters import QuotationFilter
from reservations.models import Booking, BookingHold, Quotation, QuotationLine
from reservations.serializers import (
    BookingDetailSerializer,
    QuotationDetailSerializer,
    QuotationDuplicateSerializer,
    QuotationLineSerializer,
    QuotationLineWriteSerializer,
    QuotationListSerializer,
    QuotationWriteSerializer,
)
from reservations.services.bookings import BookingService
from reservations.services.holds import HoldService
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

logger = structlog.get_logger(__name__)


# Statuses in which a quotation (header + lines) may still be edited. DRAFT is
# obvious; SENT stays open because pre-acceptance renegotiation (edit, re-send)
# is a real operator workflow. ACCEPTED/EXPIRED/CANCELLED are closed records.
_MUTABLE_QUOTATION_STATUSES = (
    QuotationStatus.DRAFT.value,
    QuotationStatus.SENT.value,
)


def _assert_quotation_mutable(quotation: Quotation) -> None:
    """409 (`quotation_locked`) when the quotation is past editing."""
    if quotation.status not in _MUTABLE_QUOTATION_STATUSES:
        raise QuotationLocked(
            f"Quotation {quotation.reference} is {quotation.status} and can no longer be edited."
        )


class QuotationViewSet(StatusCountsMixin, viewsets.ModelViewSet):
    """`/quotations` CRUD + colon-verb actions."""

    # `.real()` drops booking-synthesised quotations (`legacy_id` prefixed
    # `booking-`) — internal fixtures the data-migration loader creates so
    # legacy bookings can satisfy the QuotationLine PROTECT FK. They aren't
    # real quotes and must not surface in the public API.
    queryset = (
        Quotation.objects.real()
        .select_related(
            # GAP-045: guest name resolves from the customer Person; name only,
            # so the join suffices (no email/phone prefetch).
            "person",
            "enquiry",
            # GAP-046: agent_name falls back to the agency name, so join
            # `agent__agency` (one query, no per-row Person/Organisation lookup).
            "agent__agency",
        )
        # The detail serializer nests `lines`, each of which derives a
        # hero_image_url from its property's images, renders its own
        # currency code (GAP-014) and surfaces its live hold — prefetch the
        # whole walk so a quotation with N lines stays at a constant query
        # count. The hold prefetch filters released rows in SQL; liveness
        # (expiry) is re-checked in the serializer.
        .prefetch_related(
            "lines__property__images",
            "lines__currency",
            Prefetch(
                "lines__holds",
                queryset=BookingHold.objects.filter(released_at__isnull=True),
                to_attr="live_holds",
            ),
        )
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

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Validate with the write serializer, but echo the *detail* shape.

        DRF's default `create` re-serialises the response with the write
        serializer, which omits `id`/`status`; the SPA parses the 201 as a
        QuotationDetail and navigates to `/quotations/{id}` on save. Mirror the
        colon-verb actions (`:duplicate`, `:convert`, `:send`) and return the
        detail representation of the new row.
        """
        write = self.get_serializer(data=request.data)
        write.is_valid(raise_exception=True)
        self.perform_create(write)
        return Response(
            QuotationDetailSerializer(write.instance).data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(write.data),
        )

    def perform_create(self, serializer: Any) -> None:
        """Create header + optional nested lines atomically via the service.

        `lines` is write-only sugar on the write serializer and shadows the
        model related-name, so it must be popped before anything could reach
        `serializer.save()`. The service also mints the minimal AGENT_PORTAL
        enquiry for an agent-direct quote (no enquiry in the body), inside the
        same transaction as the lines.
        """
        header = dict(serializer.validated_data)
        lines = header.pop("lines", [])
        serializer.instance = QuotationService.create_with_lines(header, lines)

    def perform_update(self, serializer: Any) -> None:
        """Never null an existing quotation's enquiry.

        The write serializer allows a null `enquiry` only so an agent-direct
        *create* can omit it (perform_create mints one). On update the row
        always has an enquiry, so an explicit `{"enquiry": null}` body must keep
        the current one rather than 500 on the PROTECT/NOT-NULL column.
        """
        _assert_quotation_mutable(serializer.instance)
        if serializer.validated_data.get("enquiry") is None:
            serializer.validated_data.pop("enquiry", None)
        serializer.save()

    def perform_destroy(self, instance: Quotation) -> None:
        """Hard-delete is for never-sent DRAFTs only.

        A SENT quote is a customer-facing artefact (and ACCEPTED/EXPIRED/
        CANCELLED are closed records) — `:withdraw` or the expiry sweeper are
        the ways out, keeping the audit shape intact.
        """
        if instance.status != QuotationStatus.DRAFT.value:
            raise QuotationLocked(
                f"Quotation {instance.reference} is {instance.status} and can "
                "no longer be deleted — withdraw it instead."
            )
        instance.delete()

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
        """Clone header + lines into a new DRAFT quotation (SMELL-009)."""
        quotation = self.get_object()
        serializer = QuotationDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        idempotency_key = serializer.validated_data["idempotency_key"] or None
        # FG-010: the guard maps a racing loser's IntegrityError (from
        # `quotation_idempotency_key_unique_per_enquiry`) to a 409.
        with integrity_conflict_guard(
            idempotency_key,
            "A duplicate with this idempotency key already exists for this enquiry.",
        ):
            clone = QuotationService.duplicate(quotation, idempotency_key=idempotency_key)
        return Response(
            QuotationDetailSerializer(clone).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="convert")
    def convert(self, request: Request, pk: str | None = None) -> Response:
        """Convert the selected line into a Booking.

        Body: `{"line": <id>, "terms_accepted": true,
        "payment_method"?: "card"|"bank_transfer"}`.

        `terms_accepted` is the explicit acceptance signal (SMELL-006):
        `Booking.terms_accepted_at` is stamped server-side from it, never
        supplied by the client.
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
        if request.data.get("terms_accepted") is not True:
            raise TermsNotAccepted(
                "Converting a quotation requires `terms_accepted: true` — the "
                "guest's acceptance of the terms must be recorded explicitly."
            )
        line = get_object_or_404(QuotationLine, pk=line_id, quotation=quotation)
        # Only a quote the guest actually received can convert. ACCEPTED is
        # allowed solely as the double-click retry path — and only for the
        # line that was accepted; converting a *different* line would mint a
        # second booking off the same quote. DRAFT/EXPIRED/CANCELLED (holds
        # released, price possibly stale) are refused outright.
        if quotation.status == QuotationStatus.ACCEPTED:
            if not line.is_selected:
                raise QuotationLocked(
                    f"Quotation {quotation.reference} was already accepted with a different line."
                )
        elif quotation.status != QuotationStatus.SENT:
            raise InvalidTransition(
                quotation.status,
                QuotationStatus.ACCEPTED.value,
                allowed=[QuotationStatus.SENT.value],
            )
        # Accept + create must share a transaction so an `OverlappingBooking`
        # raised by the booking service rolls back the quotation acceptance,
        # otherwise the quotation gets stuck in ACCEPTED with no booking row.
        try:
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
        except IntegrityError:
            # A concurrent convert won the race past the service's
            # existing-booking pre-check and `booking_one_per_quotation_line`
            # fired. Serve the winner's row — same contract as the
            # sequential double-click retry.
            winner = Booking.objects.filter(quotation_line=line).first()
            if winner is None:
                raise
            booking = winner
        return Response(
            BookingDetailSerializer(booking).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="withdraw")
    def withdraw(self, request: Request, pk: str | None = None) -> Response:
        """Transition the quotation to CANCELLED (alias for cancel).

        Releasing the quote's holds is part of the cancel — otherwise the
        villa stays blocked on the calendar until the holds expire naturally.
        """
        quotation = self.get_object()
        reason = request.data.get("reason", "")
        with transaction.atomic():
            quotation.cancel(reason=reason)
            HoldService.release_for_quotation(quotation)
        return Response(QuotationDetailSerializer(quotation).data)


class QuotationLineViewSet(viewsets.ModelViewSet):
    """Nested `/quotations/{id}/lines` CRUD + :reorder."""

    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def get_queryset(self) -> Any:
        return (
            QuotationLine.objects.filter(quotation_id=self.kwargs["quotation_pk"])
            .real()
            .select_related("property", "currency")
            # The read serializer derives hero_image_url per line and surfaces
            # the line's live hold — prefetch both so a list of N lines stays
            # constant-query.
            .prefetch_related(
                "property__images",
                Prefetch(
                    "holds",
                    queryset=BookingHold.objects.filter(released_at__isnull=True),
                    to_attr="live_holds",
                ),
            )
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
        # `QuotationService.add_line` owns the whole recipe — currency default,
        # pricing (pinned iff a currency was supplied) — inside one
        # transaction, shared with the atomic nested-lines create path. No
        # hold: holds are a separate manual operator action.
        quotation = get_object_or_404(Quotation, pk=self.kwargs["quotation_pk"])
        _assert_quotation_mutable(quotation)
        serializer.instance = QuotationService.add_line(quotation, dict(serializer.validated_data))

    def perform_update(self, serializer: Any) -> None:
        # Persist the edited fields (adults, discount, …) BEFORE repricing so
        # `_reprice` re-reads them off the row. Without the save the patched
        # values would never reach the DB and the engine would price the stale
        # row. Then, iff the line carries a live manual hold, relocate it to
        # the edited dates — an un-held line never gains a hold from an edit.
        with transaction.atomic():
            _assert_quotation_mutable(serializer.instance.quotation)
            old_property_id = serializer.instance.property_id
            currency_supplied = serializer.validated_data.get("currency") is not None
            line = serializer.save()
            property_changed = line.property_id != old_property_id
            if property_changed and not currency_supplied and line.is_manual:
                # Currency follows the new property unless explicitly supplied.
                # Priced lines are re-stamped by the unpinned reprice below;
                # manual lines (which `_reprice` skips) re-default here so a
                # re-anchored line can't keep the old villa's currency.
                line.currency = QuotationService.default_line_currency(line.property)
                line.save(update_fields=["currency", "updated_at"])
            # Pin the line's currency on reprice so an edit (notes, discount,
            # dates) can never silently re-denominate it — a plan-currency
            # switch fails loud instead. A property change releases the pin:
            # the new villa's own plan currency should win.
            pin = None if (property_changed and not currency_supplied) else line.currency
            self._reprice(line, currency=pin)
            QuotationService.move_line_hold(line)

    def perform_destroy(self, instance: QuotationLine) -> None:
        # The lock guard is the only view-level concern here — hold release
        # stays with the `QuotationLine` pre_delete signal, which covers every
        # delete path (API, ORM, cascade).
        _assert_quotation_mutable(instance.quotation)
        instance.delete()

    def _reprice(self, line: QuotationLine, *, currency: Any = None) -> None:
        """Recompute a non-manual line's total + pricing_snapshot.

        Manual-override lines (`is_manual=True`) keep whatever total /
        pricing_snapshot the operator supplied — the manual-override write
        surface is a later phase, so for now a manual line is simply left
        untouched here.

        `currency` pins the engine to an exact-match reprice (GAP-014 / FG-001
        semantics); `None` prices in the plan's own currency.

        Per FG-006 we re-read the row under `select_for_update` inside a
        transaction before repricing, so a concurrent write to the same line
        serialises behind this update rather than racing it.
        """
        if line.is_manual:
            return
        with transaction.atomic():
            locked = (
                QuotationLine.objects.select_for_update()
                .select_related("property", "quotation")
                .get(pk=line.pk)
            )
            QuotationService.price_line(locked.quotation, locked, currency=currency)
        # Reflect the persisted price back onto the serializer's instance so
        # the response (built from it) carries the server-computed values —
        # including any changeover-shifted dates (GAP-007) and the currency
        # the engine actually priced in (GAP-014).
        line.total = locked.total
        line.pricing_snapshot = locked.pricing_snapshot
        line.currency = locked.currency
        line.date_from = locked.date_from
        line.date_to = locked.date_to

    @action(detail=True, methods=["post"], url_path="hold")
    def hold(
        self, request: Request, quotation_pk: str | None = None, pk: str | None = None
    ) -> Response:
        """Place the line's manual availability hold (idempotent).

        Holds are significant — they block the villa's dates for everyone —
        so they are never a side effect of quoting; this endpoint is the
        operator's deliberate action. 409 `hold_unavailable` if another live
        hold owns the dates; 409 `quotation_locked` past DRAFT/SENT.
        """
        line = self.get_object()
        _assert_quotation_mutable(line.quotation)
        QuotationService.hold_line(line, actor=request.user)
        return Response(QuotationLineSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="release-hold")
    def release_hold(
        self, request: Request, quotation_pk: str | None = None, pk: str | None = None
    ) -> Response:
        """Release the line's live hold (idempotent).

        Deliberately NOT status-guarded: a hold has its own expiry and may
        outlive its quotation — freeing inventory must always be possible.
        """
        line = self.get_object()
        QuotationService.release_line_hold(line, actor=request.user)
        return Response(QuotationLineSerializer(self.get_object()).data)

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
