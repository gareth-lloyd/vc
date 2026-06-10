"""Views for `PropertyImage` — list/create/detail and reorder/set-hero actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import IsReservationsWriter
from properties.enums import ImageKind
from properties.models import Property, PropertyImage
from properties.serializers import (
    PropertyImageReorderSerializer,
    PropertyImageSerializer,
    PropertyImageSetHeroSerializer,
    PropertyImageWriteSerializer,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


class PropertyImageListCreateView(generics.ListAPIView):
    """List for GET; POST uploads an image (multipart) and attaches it."""

    serializer_class = PropertyImageSerializer
    permission_classes = [IsReservationsWriter]
    # The default parser set is JSON-only; the upload arrives as multipart.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self) -> QuerySet[PropertyImage]:
        return PropertyImage.objects.filter(property_id=self.kwargs["property_id"])

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        write = PropertyImageWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        data = write.validated_data
        image = PropertyImage.objects.create(
            property=property_obj,
            image=data["image"],
            kind=data["kind"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            sort_order=data.get("sort_order", 0),
            is_active=data.get("is_active", True),
        )
        return Response(
            PropertyImageSerializer(image).data,
            status=status.HTTP_201_CREATED,
        )


class PropertyImageDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PropertyImageSerializer
    permission_classes = [IsReservationsWriter]
    lookup_url_kwarg = "image_id"

    def get_queryset(self) -> QuerySet[PropertyImage]:
        return PropertyImage.objects.filter(property_id=self.kwargs["property_id"])


class PropertyImageReorderView(APIView):
    """Body: `{image_ids: [int, ...]}` — assigns `sort_order` by position."""

    permission_classes = [IsReservationsWriter]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = PropertyImageReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        property_id = self.kwargs["property_id"]
        get_object_or_404(Property, pk=property_id)
        ids: list[int] = serializer.validated_data["image_ids"]
        with transaction.atomic():
            for position, image_id in enumerate(ids):
                PropertyImage.objects.filter(
                    pk=image_id,
                    property_id=property_id,
                ).update(sort_order=position)
        return Response(
            PropertyImageSerializer(
                PropertyImage.objects.filter(property_id=property_id),
                many=True,
            ).data
        )


class PropertyImageSetHeroView(APIView):
    """Body: `{image_id: int}` — flips this image to HERO, clears prior hero."""

    permission_classes = [IsReservationsWriter]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = PropertyImageSetHeroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        property_id = self.kwargs["property_id"]
        image_id = serializer.validated_data["image_id"]
        with transaction.atomic():
            # Demote previous active hero (the unique index forbids two active heros).
            PropertyImage.objects.filter(
                property_id=property_id,
                kind=ImageKind.HERO,
                is_active=True,
            ).exclude(pk=image_id).update(kind=ImageKind.GALLERY)
            image = get_object_or_404(
                PropertyImage,
                pk=image_id,
                property_id=property_id,
            )
            image.kind = ImageKind.HERO
            image.is_active = True
            image.save(update_fields=["kind", "is_active", "updated_at"])
        return Response(PropertyImageSerializer(image).data)
