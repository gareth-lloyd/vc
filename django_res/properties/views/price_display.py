"""Stub view for `/properties/{id}/price-display`.

The legacy data model spreads price-display knobs across `PropertyFinance` and
`PropertySettings`. For v1 we surface a tiny dedicated resource backed by
in-memory defaults; the FE wires up its read/write behaviour without locking
in a schema we'll regret.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import IsReservationsWriter
from properties.models import Property
from properties.serializers import PropertyPriceDisplaySerializer

if TYPE_CHECKING:
    from rest_framework.request import Request


_DEFAULTS: dict[str, Any] = {
    "poa": False,
    "show_min": True,
    "show_max": False,
    "symbol_position": "leading",
}


class PropertyPriceDisplayView(APIView):
    permission_classes = [IsReservationsWriter]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        get_object_or_404(Property, pk=self.kwargs["property_id"])
        return Response(_DEFAULTS)

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        get_object_or_404(Property, pk=self.kwargs["property_id"])
        serializer = PropertyPriceDisplaySerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        merged = {**_DEFAULTS, **serializer.validated_data}
        return Response(merged)
