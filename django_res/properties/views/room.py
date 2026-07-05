"""Views for `Room` — list/create, detail, reorder — plus the RoomAttribute
catalog."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import generics, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import (
    AllowAnyReadStaffWrite,
    ConfigurablePageSizePagination,
    IsReservationsWriter,
)
from properties.models import Property, Room, RoomAttribute, RoomAttributeAssignment
from properties.serializers import RoomAttributeSerializer, RoomSerializer

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


def _room_queryset(property_id: Any) -> QuerySet[Room]:
    """Everything RoomSerializer walks: beds + amenity links in catalog rank
    (display order lives in this Prefetch, not the through model's Meta)."""
    return (
        Room.objects.filter(property_id=property_id)
        .select_related("beds")
        .prefetch_related(
            Prefetch(
                "attribute_links",
                queryset=RoomAttributeAssignment.objects.select_related("attribute").order_by(
                    "attribute__sort_order", "attribute__name"
                ),
            )
        )
    )


class PropertyRoomListCreateView(generics.ListCreateAPIView):
    serializer_class = RoomSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[Room]:
        return _room_queryset(self.kwargs["property_id"])

    def perform_create(self, serializer: Any) -> None:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        serializer.save(property=property_obj)
        # Re-serialize the response from the read queryset: a fresh instance
        # has no prefetch cache, so `attribute_links` would otherwise render
        # via the bare manager — one query per attribute and id-order instead
        # of catalog rank.
        serializer.instance = self.get_queryset().get(pk=serializer.instance.pk)


class RoomDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RoomSerializer
    permission_classes = [IsReservationsWriter]
    lookup_url_kwarg = "room_id"

    def get_queryset(self) -> QuerySet[Room]:
        return _room_queryset(self.kwargs["property_id"])

    def perform_update(self, serializer: Any) -> None:
        serializer.save()
        # Same rationale as perform_create: DRF resets the prefetch cache
        # after an update, so re-fetch through the read queryset to keep the
        # response's link order and query count identical to GET.
        serializer.instance = self.get_queryset().get(pk=serializer.instance.pk)


class PropertyRoomReorderView(APIView):
    """Body: `{room_ids: [int, ...]}`."""

    permission_classes = [IsReservationsWriter]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        ids = request.data.get("room_ids") if isinstance(request.data, dict) else None
        if not isinstance(ids, list) or not ids:
            return Response(
                {
                    "code": "validation_error",
                    "detail": "room_ids must be a non-empty list",
                    "field_errors": {"room_ids": ["required"]},
                },
                status=400,
            )
        property_id = self.kwargs["property_id"]
        with transaction.atomic():
            for position, room_id in enumerate(ids):
                Room.objects.filter(pk=room_id, property_id=property_id).update(sort_order=position)
        return Response(RoomSerializer(_room_queryset(property_id), many=True).data)


class RoomAttributeViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only — the amenity catalog is migration-seeded and curated in the
    Django admin. Serves inactive rows too: the room form must keep
    retired-but-assigned attributes ticked (filtering is the client's job)."""

    queryset = RoomAttribute.objects.all()
    serializer_class = RoomAttributeSerializer
    permission_classes = [AllowAnyReadStaffWrite]
    # The room form fetches the whole catalog in one request (the taxonomy
    # picker pattern); honour its `page_size` so growth past the default page
    # never silently truncates the amenity list.
    pagination_class = ConfigurablePageSizePagination
