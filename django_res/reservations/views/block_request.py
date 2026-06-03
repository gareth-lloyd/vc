"""Operator-facing review surface for owner block requests (`/block-requests`).

Staff approve or decline the requests owners raise via `/owner/block-requests`.
Approval is where the indefinite `BookingHold` is placed — see
`OwnerBlockRequestService`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.api.permissions import IsReservationsWriter
from reservations.models import OwnerBlockRequest
from reservations.serializers.owner import OperatorBlockRequestSerializer
from reservations.services.owner_block_requests import OwnerBlockRequestService

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request

    from accounts.models import User


class BlockRequestViewSet(viewsets.GenericViewSet):
    """`/block-requests` — staff queue + approve/decline actions.

    Read for any staff user; approve/decline for ADMIN/RESERVATIONS roles
    (enforced by `IsReservationsWriter` on the unsafe methods).
    """

    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def get_queryset(self) -> QuerySet[OwnerBlockRequest]:
        return OwnerBlockRequest.objects.select_related(
            "property", "requested_by", "reviewed_by"
        ).order_by("-created_at")

    def list(self, request: Request) -> Response:
        qs = self.get_queryset()
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        property_id = request.query_params.get("property")
        if property_id:
            qs = qs.filter(property_id=property_id)
        return Response(OperatorBlockRequestSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request: Request, pk: str | None = None) -> Response:
        block_request = get_object_or_404(OwnerBlockRequest, pk=pk)
        OwnerBlockRequestService.approve(
            block_request,
            actor=cast("User", request.user),
            review_note=request.data.get("review_note", ""),
        )
        return Response(OperatorBlockRequestSerializer(block_request).data)

    @action(detail=True, methods=["post"], url_path="decline")
    def decline(self, request: Request, pk: str | None = None) -> Response:
        block_request = get_object_or_404(OwnerBlockRequest, pk=pk)
        OwnerBlockRequestService.decline(
            block_request,
            request.data.get("review_note", ""),
            actor=cast("User", request.user),
        )
        return Response(OperatorBlockRequestSerializer(block_request).data)
