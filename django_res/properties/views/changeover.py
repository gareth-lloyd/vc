"""Views for `ChangeOverRule`."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework import generics

from core.api import IsReservationsWriter
from properties.models import ChangeOverRule, Property
from properties.serializers import ChangeOverRuleSerializer

if TYPE_CHECKING:
    from django.db.models import QuerySet


class PropertyChangeOverRuleListCreateView(generics.ListCreateAPIView):
    serializer_class = ChangeOverRuleSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[ChangeOverRule]:
        qs = ChangeOverRule.objects.filter(property_id=self.kwargs["property_id"])
        effective_on = self.request.query_params.get("effective_on")
        if effective_on:
            try:
                day = date.fromisoformat(effective_on)
                qs = qs.filter(starts_on__lte=day, ends_on__gte=day)
            except ValueError:
                qs = qs.none()
        return qs

    def perform_create(self, serializer: Any) -> None:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        serializer.save(property=property_obj)


class ChangeOverRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ChangeOverRule.objects.all()
    serializer_class = ChangeOverRuleSerializer
    permission_classes = [IsReservationsWriter]
