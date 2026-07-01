"""Views for `Discount` (global, property-nested, card-nested) + lookup."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework import generics, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import IsReservationsWriter, IsStaff
from pricing.enums import RuleKind
from pricing.filters import DiscountFilter
from pricing.models import Discount
from pricing.serializers import (
    DiscountLookupCodeSerializer,
    DiscountSerializer,
)
from properties.models import Property

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


class DiscountViewSet(viewsets.ModelViewSet):
    queryset = Discount.objects.all()
    serializer_class = DiscountSerializer
    permission_classes = [IsReservationsWriter]
    filterset_class = DiscountFilter


class PropertyDiscountListCreateView(generics.ListCreateAPIView):
    """`GET / POST /properties/{id}/discounts` — sets `property` from path."""

    serializer_class = DiscountSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[Discount]:
        return Discount.objects.filter(property_id=self.kwargs["property_id"])

    def perform_create(self, serializer: Any) -> None:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        serializer.save(property=property_obj)


class DiscountLookupCodeView(APIView):
    """`POST /discounts:lookup-code` — validate a promo code."""

    permission_classes = [IsStaff]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = DiscountLookupCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        date_from: date = data["date_from"]
        code = data["code"]
        match = (
            Discount.objects.filter(
                property_id=data["property_id"],
                rule_kind=RuleKind.PROMO_CODE.value,
                code__iexact=code,
                is_active=True,
                valid_from__lte=date_from,
                valid_to__gte=date_from,
            )
            .order_by("-pk")
            .first()
        )
        if match is None:
            return Response(
                {"code": "not_found", "detail": "code not valid", "field_errors": {}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "discount_id": match.pk,
                "name": match.name,
                "kind": match.kind,
                "amount": str(match.amount),
                "applies": True,
            }
        )
