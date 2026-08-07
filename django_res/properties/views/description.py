"""Views for `PropertyDescription` (rich-text section blocks)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response

from core.api import IsReservationsWriter
from properties.enums import DescriptionSection
from properties.models import Property, PropertyDescription
from properties.serializers import (
    PropertyDescriptionSerializer,
    PropertyDescriptionWriteSerializer,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


class PropertyDescriptionListView(generics.ListAPIView):
    """GET `/properties/{id}/descriptions` — every present section."""

    serializer_class = PropertyDescriptionSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[PropertyDescription]:
        return PropertyDescription.objects.filter(property_id=self.kwargs["property_id"])


class PropertyDescriptionDetailView(generics.GenericAPIView):
    """GET / PUT / DELETE one section block. PUT upserts."""

    serializer_class = PropertyDescriptionSerializer
    permission_classes = [IsReservationsWriter]
    lookup_field = "section"

    def _validate_section(self, section: str) -> str:
        if section.replace("-", "_") not in DescriptionSection.values:
            return ""
        return section.replace("-", "_")

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        section = self._validate_section(self.kwargs["section"])
        if not section:
            return Response(
                {"code": "not_found", "detail": "unknown section", "field_errors": {}},
                status=status.HTTP_404_NOT_FOUND,
            )
        instance = get_object_or_404(
            PropertyDescription,
            property_id=self.kwargs["property_id"],
            section=section,
        )
        return Response(PropertyDescriptionSerializer(instance).data)

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        section = self._validate_section(self.kwargs["section"])
        if not section:
            return Response(
                {"code": "not_found", "detail": "unknown section", "field_errors": {}},
                status=status.HTTP_404_NOT_FOUND,
            )
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        write = PropertyDescriptionWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        instance, created = PropertyDescription.objects.get_or_create(
            property=property_obj,
            section=section,
            defaults={"body": write.validated_data["body"]},
        )
        if not created:
            instance.body = write.validated_data["body"]
            # Deliberately not `update_or_create`: its update path saves with
            # `update_fields` covering only `defaults` + auto_now columns, so the
            # `updated_by` that `core.signals.populate_user_fields` assigns is
            # discarded and an edited section keeps its original author.
            instance.save(update_fields=["body", "updated_at", "updated_by"])
        code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(PropertyDescriptionSerializer(instance).data, status=code)

    def delete(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        section = self._validate_section(self.kwargs["section"])
        if not section:
            return Response(
                {"code": "not_found", "detail": "unknown section", "field_errors": {}},
                status=status.HTTP_404_NOT_FOUND,
            )
        PropertyDescription.objects.filter(
            property_id=self.kwargs["property_id"],
            section=section,
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
