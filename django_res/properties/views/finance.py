"""Views for `PropertyFinance` and `GroupFinance` (one-row-per-parent)."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics

from core.api import IsReservationsWriter
from properties.models import (
    GroupFinance,
    Property,
    PropertyFinance,
    PropertyGroup,
)
from properties.serializers import GroupFinanceSerializer, PropertyFinanceSerializer


class PropertyFinanceView(generics.RetrieveUpdateAPIView):
    serializer_class = PropertyFinanceSerializer
    permission_classes = [IsReservationsWriter]

    def get_object(self) -> PropertyFinance:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        instance, _ = PropertyFinance.objects.get_or_create(property=property_obj)
        return instance


class GroupFinanceView(generics.RetrieveUpdateAPIView):
    serializer_class = GroupFinanceSerializer
    permission_classes = [IsReservationsWriter]

    def get_object(self) -> GroupFinance:
        group = get_object_or_404(PropertyGroup, pk=self.kwargs["group_id"])
        instance, _ = GroupFinance.objects.get_or_create(group=group)
        return instance
