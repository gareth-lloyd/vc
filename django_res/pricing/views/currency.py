"""Views for `Currency` + its nested FxRate list."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.shortcuts import get_object_or_404
from rest_framework import generics, viewsets

from core.api import AllowAnyReadStaffWrite
from pricing.models import Currency, FxRate
from pricing.serializers import CurrencySerializer, FxRateSerializer

if TYPE_CHECKING:
    from django.db.models import QuerySet


class CurrencyViewSet(viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    permission_classes = [AllowAnyReadStaffWrite]
    lookup_field = "code"


class CurrencyFxRatesView(generics.ListAPIView):
    serializer_class = FxRateSerializer
    permission_classes = [AllowAnyReadStaffWrite]

    def get_queryset(self) -> QuerySet[FxRate]:
        currency = get_object_or_404(Currency, code=self.kwargs["code"])
        return FxRate.objects.filter(base=currency)
