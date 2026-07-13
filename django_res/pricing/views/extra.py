"""Views for `Extra` — property-scoped CRUD plus duplicate action."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import IsReservationsWriter
from core.exceptions import IdempotencyConflict
from pricing.models import Extra
from pricing.serializers import ExtraDuplicateSerializer, ExtraSerializer
from pricing.services.duplication import duplicate_extra
from properties.models import Property

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


class PropertyExtraListCreateView(generics.ListCreateAPIView):
    serializer_class = ExtraSerializer
    permission_classes = [IsReservationsWriter]
    filterset_fields = ["kind", "is_mandatory", "commissionable", "is_active"]

    def get_queryset(self) -> QuerySet[Extra]:
        return Extra.objects.filter(property_id=self.kwargs["property_id"]).select_related(
            "currency"
        )

    def perform_create(self, serializer: Any) -> None:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        serializer.save(property=property_obj)


class ExtraDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Extra.objects.select_related("currency")
    serializer_class = ExtraSerializer
    permission_classes = [IsReservationsWriter]


class ExtraDuplicateView(APIView):
    """`POST /extras/{id}:duplicate` — clone, optionally cross-property (SMELL-009)."""

    permission_classes = [IsReservationsWriter]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        original = get_object_or_404(Extra, pk=self.kwargs["pk"])
        serializer = ExtraDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_id = serializer.validated_data.get("target_property_id")
        target_property = get_object_or_404(Property, pk=target_id) if target_id else None
        idempotency_key = serializer.validated_data["idempotency_key"] or None
        try:
            clone = duplicate_extra(
                original,
                target_property=target_property,
                idempotency_key=idempotency_key,
            )
        except IntegrityError as exc:
            # FG-010: two racing requests with the same key both pass the
            # service pre-check under READ COMMITTED; the loser hits
            # `extra_idempotency_key_unique_per_property`. Keyless requests
            # can't trip the partial-unique backstop, so theirs is a genuine
            # error, not a conflict.
            if idempotency_key is None:
                raise
            raise IdempotencyConflict(
                "A duplicate with this idempotency key already exists for this property."
            ) from exc
        return Response(ExtraSerializer(clone).data, status=status.HTTP_201_CREATED)
