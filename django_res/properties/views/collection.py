"""Views for `Collection` and `CollectionMembership`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework import generics, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import AllowAnyReadStaffWrite, IsReservationsWriter
from properties.models import Collection, CollectionMembership, Property
from properties.serializers import (
    CollectionMembershipSerializer,
    CollectionMembershipWriteSerializer,
    CollectionSerializer,
)
from properties.services import PropertyLifecycleService

if TYPE_CHECKING:
    from rest_framework.request import Request


class CollectionViewSet(viewsets.ModelViewSet):
    queryset = Collection.objects.all()
    serializer_class = CollectionSerializer
    permission_classes = [AllowAnyReadStaffWrite]
    lookup_field = "slug"


class PropertyCollectionsView(APIView):
    """`GET / PUT / POST` on `/properties/{id}/collections`."""

    permission_classes = [IsReservationsWriter]

    def _resolve_collection(self, value: str | int) -> Collection:
        if isinstance(value, int) or (isinstance(value, str) and str(value).isdigit()):
            return get_object_or_404(Collection, pk=int(value))
        return get_object_or_404(Collection, slug=value)

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        memberships = CollectionMembership.objects.filter(
            property_id=self.kwargs["property_id"]
        ).select_related("collection")
        return Response(CollectionMembershipSerializer(memberships, many=True).data)

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        body: list[Any] = request.data if isinstance(request.data, list) else []
        write = CollectionMembershipWriteSerializer(data=body, many=True)
        write.is_valid(raise_exception=True)
        memberships = PropertyLifecycleService.replace_collection_memberships(
            property_obj, write.validated_data
        )
        return Response(CollectionMembershipSerializer(memberships, many=True).data)

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        write = CollectionMembershipWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        data = write.validated_data
        collection = self._resolve_collection(data["collection"])
        membership, _ = CollectionMembership.objects.update_or_create(
            property=property_obj,
            collection=collection,
            defaults={
                "sort_order": data.get("sort_order", 0),
                "featured_until": data.get("featured_until"),
                "description": data.get("description", ""),
            },
        )
        return Response(
            CollectionMembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )


class CollectionMembershipDetailView(generics.GenericAPIView):
    """`PATCH / DELETE` on `/properties/{id}/collections/{collection}`."""

    permission_classes = [IsReservationsWriter]
    serializer_class = CollectionMembershipSerializer

    def _get_membership(self) -> CollectionMembership:
        property_id = self.kwargs["property_id"]
        collection = self.kwargs["collection"]
        qs = CollectionMembership.objects.filter(property_id=property_id)
        if str(collection).isdigit():
            return get_object_or_404(qs, collection_id=int(collection))
        return get_object_or_404(qs, collection__slug=collection)

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        membership = self._get_membership()
        for field in ("sort_order", "featured_until", "description"):
            if isinstance(request.data, dict) and field in request.data:
                setattr(membership, field, request.data[field])
        membership.save()
        return Response(CollectionMembershipSerializer(membership).data)

    def delete(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        membership = self._get_membership()
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CollectionPropertiesView(APIView):
    """`GET /collections/{slug}/properties` and `PUT` for full-set replace."""

    permission_classes = [IsReservationsWriter]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        collection = get_object_or_404(Collection, slug=self.kwargs["slug"])
        memberships = CollectionMembership.objects.filter(collection=collection)
        return Response(CollectionMembershipSerializer(memberships, many=True).data)

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        collection = get_object_or_404(Collection, slug=self.kwargs["slug"])
        body: list[Any] = request.data if isinstance(request.data, list) else []
        keep_ids: list[int] = []
        for entry in body:
            if not isinstance(entry, dict):
                continue
            property_ref = entry.get("property")
            if property_ref is None:
                continue
            if str(property_ref).isdigit():
                property_obj = get_object_or_404(Property, pk=int(property_ref))
            else:
                property_obj = get_object_or_404(Property, slug=property_ref)
            membership, _ = CollectionMembership.objects.update_or_create(
                collection=collection,
                property=property_obj,
                defaults={
                    "sort_order": entry.get("sort_order", 0),
                    "featured_until": entry.get("featured_until"),
                    "description": entry.get("description", ""),
                },
            )
            keep_ids.append(membership.pk)
        CollectionMembership.objects.filter(collection=collection).exclude(pk__in=keep_ids).delete()
        return Response(
            CollectionMembershipSerializer(
                CollectionMembership.objects.filter(collection=collection),
                many=True,
            ).data
        )
