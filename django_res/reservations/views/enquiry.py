"""Viewsets for /enquiries — CRUD plus :assign, :convert, :close, :reopen."""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import User
from core.api.permissions import IsReservationsWriter
from reservations.filters import EnquiryFilter
from reservations.models import Enquiry, EnquiryEvent, EnquiryNote
from reservations.serializers import (
    EnquiryDetailSerializer,
    EnquiryEventSerializer,
    EnquiryListSerializer,
    EnquiryNoteSerializer,
    EnquiryWriteSerializer,
)


class EnquiryViewSet(viewsets.ModelViewSet):
    """`/enquiries` CRUD plus colon-verb action endpoints."""

    queryset = Enquiry.objects.all()
    permission_classes = [IsAuthenticated, IsReservationsWriter]
    filterset_class = EnquiryFilter
    ordering_fields = ["created_at", "updated_at", "status"]
    ordering = ["-created_at"]

    def get_serializer_class(self) -> type:
        if self.action in ("list",):
            return EnquiryListSerializer
        if self.action in ("create", "update", "partial_update"):
            return EnquiryWriteSerializer
        return EnquiryDetailSerializer

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
        """Convert this enquiry — body: `{"quotation": <id>}`."""
        from reservations.models import Quotation

        enquiry = self.get_object()
        quotation_id = request.data.get("quotation")
        quotation = get_object_or_404(Quotation, pk=quotation_id)
        enquiry.convert(quotation, actor=request.user)
        return Response(EnquiryDetailSerializer(enquiry).data)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request: Request, pk: str | None = None) -> Response:
        """Mark closed-lost. Body: `{"reason": "..."}`."""
        enquiry = self.get_object()
        reason = request.data.get("reason", "")
        enquiry.lose(reason=reason, actor=request.user)
        return Response(EnquiryDetailSerializer(enquiry).data)

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
