"""`/bookings/{id}/emails` — per-booking EmailLog list + resend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comms.models import EmailLog
from comms.serializers import EmailLogSerializer
from comms.services import EmailService
from core.api.permissions import IsReservationsWriter

if TYPE_CHECKING:
    from accounts.models import User


class BookingEmailViewSet(viewsets.GenericViewSet):
    """Booking-scoped EmailLog read + resend.

    EmailLog isn't linked to Booking via a FK; the relationship lives in
    `EmailLog.correlation["booking_id"]`. The viewset filters by that
    JSON key and exposes a `:resend` action that mints a new EmailLog
    row carrying the same content + recipient set.
    """

    serializer_class = EmailLogSerializer
    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def get_queryset(self) -> Any:
        booking_id = int(self.kwargs["booking_pk"])
        return (
            EmailLog.objects.filter(correlation__booking_id=booking_id)
            .select_related("sender_user", "smtp_profile")
            .order_by("-queued_at", "-id")
        )

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(queryset, many=True).data)

    @action(detail=True, methods=["post"], url_path="resend")
    def resend(
        self,
        request: Request,
        booking_pk: str | None = None,
        pk: str | None = None,
    ) -> Response:
        """Mint a new EmailLog row carrying the same content + recipients.

        Idempotency: caller supplies `idempotency_key` (a uuid). A repeat
        call with the same key returns the previously-minted resend
        instead of double-sending.
        """
        email_log = get_object_or_404(self.get_queryset(), pk=pk)
        # IsAuthenticated has already filtered out AnonymousUser at this
        # point, so the actor is always a concrete User.
        actor = cast("User", request.user)
        new_log = EmailService.resend(
            email_log,
            actor=actor,
            idempotency_key=request.data.get("idempotency_key") or None,
        )
        return Response(
            EmailLogSerializer(new_log).data,
            status=status.HTTP_201_CREATED,
        )
