"""Flat Payment list / detail surface (`/payments`)."""

from __future__ import annotations

from typing import Any

from rest_framework import mixins, viewsets

from core.api import IsStaff
from payments.filters import PaymentFilter
from payments.models import Payment
from payments.serializers import PaymentSerializer


class PaymentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only flat list/detail across every track."""

    serializer_class = PaymentSerializer
    permission_classes = [IsStaff]
    filterset_class = PaymentFilter
    ordering_fields = ["created_at", "settled_at", "due_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self) -> Any:
        return Payment.objects.select_related(
            "booking",
            "currency",
            "concierge_item",
        )
