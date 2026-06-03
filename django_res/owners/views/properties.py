"""Scoped, read-only owner properties endpoint (`/owner/properties`)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.db.models import Prefetch
from rest_framework import viewsets

from owners.permissions import IsOwner
from owners.scoping import owner_property_ids
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

    def get_queryset(self) -> QuerySet[Property]:
        user = cast("User", self.request.user)
        hero_images = PropertyImage.objects.filter(kind=ImageKind.HERO, is_active=True)
        return (
            Property.objects.filter(id__in=owner_property_ids(user))
            .select_related("category", "group", "region", "capacity")
            .prefetch_related(Prefetch("images", queryset=hero_images))
            .order_by("name")
        )
