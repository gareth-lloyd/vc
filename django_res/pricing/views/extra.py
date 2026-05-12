"""Views for `Extra` — property-scoped CRUD plus duplicate action."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import IsReservationsWriter
from pricing.models import Extra
from pricing.serializers import ExtraSerializer
from properties.models import Property

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


class PropertyExtraListCreateView(generics.ListCreateAPIView):
    serializer_class = ExtraSerializer
    permission_classes = [IsReservationsWriter]
    filterset_fields = ["kind", "is_mandatory", "is_active"]

    def get_queryset(self) -> QuerySet[Extra]:
        return Extra.objects.filter(property_id=self.kwargs["property_id"])

    def perform_create(self, serializer: Any) -> None:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        serializer.save(property=property_obj)


class ExtraDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Extra.objects.all()
    serializer_class = ExtraSerializer
    permission_classes = [IsReservationsWriter]


class ExtraDuplicateView(APIView):
    permission_classes = [IsReservationsWriter]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        original = get_object_or_404(Extra, pk=self.kwargs["pk"])
        clone = Extra.objects.get(pk=original.pk)
        clone.pk = None
        target = request.data.get("target_property_id") if isinstance(request.data, dict) else None
        if target:
            target_property = get_object_or_404(Property, pk=int(target))
            clone.property = target_property
        clone.name = f"{original.name} (copy)"
        clone.save()
        return Response(ExtraSerializer(clone).data, status=status.HTTP_201_CREATED)
