"""Scoped, read-only owner properties endpoint (`/owner/properties`)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.db.models import Prefetch
from rest_framework import viewsets

from owners.permissions import IsOwner
from owners.scoping import (
    BLOCK_WRITER_ROLES,
    owner_property_ids,
    owner_property_ids_for_roles,
)
from owners.serializers.property import OwnerPropertySerializer
from properties.enums import ImageKind
from properties.models import Property, PropertyImage

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from accounts.models import User


class OwnerPropertyViewSet(viewsets.ReadOnlyModelViewSet):
    """List + retrieve the villas the caller's orgs may view.

    Scoping is server-side: `get_queryset` restricts to `owner_property_ids`,
    so a retrieve of any other property 404s rather than leaking existence.
    """

    serializer_class = OwnerPropertySerializer
    permission_classes = [IsOwner]

    def get_serializer_context(self) -> dict[str, object]:
        context = super().get_serializer_context()
        context["block_writer_property_ids"] = owner_property_ids_for_roles(
            cast("User", self.request.user), BLOCK_WRITER_ROLES
        )
        return context

    def get_queryset(self) -> QuerySet[Property]:
        user = cast("User", self.request.user)
        hero_images = PropertyImage.objects.filter(kind=ImageKind.HERO, is_active=True)
        return (
            Property.objects.filter(id__in=owner_property_ids(user))
            .select_related("category", "region", "capacity")
            .prefetch_related(Prefetch("images", queryset=hero_images))
            .order_by("name")
        )
