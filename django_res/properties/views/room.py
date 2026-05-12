"""Views for `Room` — list/create, detail, reorder."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import IsReservationsWriter
from properties.models import Property, Room
from properties.serializers import RoomSerializer

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


class PropertyRoomListCreateView(generics.ListCreateAPIView):
    serializer_class = RoomSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[Room]:
        return Room.objects.filter(property_id=self.kwargs["property_id"]).select_related("beds")

    def perform_create(self, serializer: Any) -> None:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        serializer.save(property=property_obj)


class RoomDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RoomSerializer
    permission_classes = [IsReservationsWriter]
    lookup_url_kwarg = "room_id"

    def get_queryset(self) -> QuerySet[Room]:
        return Room.objects.filter(property_id=self.kwargs["property_id"]).select_related("beds")


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
        return Response(
            RoomSerializer(Room.objects.filter(property_id=property_id), many=True).data
        )
