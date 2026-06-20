"""DRF viewset for `Property` (CRUD + lifecycle actions).

Business logic lives in `properties.services.PropertyLifecycleService`; the
view is a thin orchestrator around it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.api import IsReservationsWriter, IsStaff, not_implemented_response
from properties.filters import PropertyFilter
from properties.filters.property import (
    include_unavailable_requested,
    parse_availability_range,
    unavailable_property_ids,
)
from properties.models import Property, PropertyCalendarFeed
from properties.serializers import (
    PropertyDetailSerializer,
    PropertyListSerializer,
    PropertyWriteSerializer,
)
from properties.services import PropertyLifecycleService
from properties.services.location import ensure_property_location

if TYPE_CHECKING:
    from rest_framework.request import Request


class PropertyViewSet(viewsets.ModelViewSet):
    """Core property CRUD plus lifecycle action endpoints.

    Detail lookup accepts either a numeric pk or a slug — the matcher is in
    `get_object`.
    """

    queryset = (
        Property.objects.all()
        .select_related("category", "group", "region", "capacity", "settings")
        # Scalar `Exists` subquery → no JOIN, no row multiplication, so the
        # paginator COUNT(*) stays correct and the list flag costs no per-row
        # query (GAP-034). `_CalendarSourceMixin` reads this annotation, falling
        # back to `.exists()` for fresh `create`/`duplicate` instances.
        .annotate(
            has_active_ical_feed=Exists(
                PropertyCalendarFeed.objects.filter(property=OuterRef("pk"), is_active=True)
            )
        )
    )
    filterset_class = PropertyFilter
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    ordering_fields = ["name", "display_name", "created_at", "updated_at"]
    # Default ordering (incl. the `id` pagination tiebreaker) comes from
    # Property.Meta.ordering, so every paginated listing stays stable.
    permission_classes = [IsReservationsWriter]

    def get_permissions(self) -> list[Any]:
        if self.action in {"list", "retrieve"}:
            return [IsStaff()]
        return [IsReservationsWriter()]

    def get_serializer_class(self) -> type[Any]:
        if self.action in {"list"}:
            return PropertyListSerializer
        if self.action in {"create", "update", "partial_update"}:
            return PropertyWriteSerializer
        return PropertyDetailSerializer

    def get_serializer_context(self) -> dict[str, Any]:
        """List requests with a date range get the bulk unavailable-id set.

        `PropertyListSerializer.available_for_range` reads it. The shared
        `parse_availability_range` keeps the per-row flag and the
        row-exclusion filter agreeing on what "a date range" is.
        """
        context = super().get_serializer_context()
        if self.action != "list":
            return context
        params = self.request.query_params
        date_range = parse_availability_range(params)
        if date_range is None:
            return context
        if include_unavailable_requested(params):
            context["unavailable_property_ids"] = unavailable_property_ids(*date_range)
        else:
            # The availability filter already excluded unavailable rows, so
            # every surviving row is available — no second conflict query.
            context["unavailable_property_ids"] = frozenset()
        return context

    def get_object(self) -> Property:
        """Look up by numeric pk or slug. Mirrors the spec's dual-key shape."""
        lookup = self.kwargs[self.lookup_field]
        qs = self.filter_queryset(self.get_queryset())
        if str(lookup).isdigit():
            return get_object_or_404(qs, pk=int(lookup))
        return get_object_or_404(qs, slug=str(lookup))

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        write_serializer = PropertyWriteSerializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        # Atomic so a failure provisioning the location never leaves a
        # committed-but-location-less property (the state this feature removes).
        with transaction.atomic():
            instance = write_serializer.save()
            # Provision a default location so the new property's address/timezone
            # are immediately editable (consistent with the loader/factory).
            ensure_property_location(instance)
        read_serializer = PropertyDetailSerializer(instance)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        write_serializer = PropertyWriteSerializer(instance, data=request.data, partial=partial)
        write_serializer.is_valid(raise_exception=True)
        instance = write_serializer.save()
        return Response(PropertyDetailSerializer(instance).data)

    # ------------------------------------------------------------------
    # Lifecycle actions (`POST /properties/{id}:<verb>`)
    # ------------------------------------------------------------------
    def _action_response(self, instance: Property) -> Response:
        return Response(PropertyDetailSerializer(instance).data)

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        PropertyLifecycleService.activate(instance)
        return self._action_response(instance)

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        PropertyLifecycleService.archive(instance)
        return self._action_response(instance)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        PropertyLifecycleService.restore(instance)
        return self._action_response(instance)

    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        new_slug = request.data.get("slug") if isinstance(request.data, dict) else None
        clone = PropertyLifecycleService.duplicate(instance, new_slug=new_slug)
        return Response(
            PropertyDetailSerializer(clone).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="import-from-zoho")
    def import_from_zoho(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return not_implemented_response(
            "Zoho property import is not implemented in v1; tracked under issue #21."
        )
