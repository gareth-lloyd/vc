"""Serializers for `Collection` and `CollectionMembership`."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import Collection, CollectionMembership


class CollectionSerializer(serializers.ModelSerializer[Collection]):
    class Meta:
        model = Collection
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "sort_order",
            "is_active",
        ]
        read_only_fields = ["id"]


class CollectionMembershipSerializer(serializers.ModelSerializer[CollectionMembership]):
    """Read shape for membership rows on `GET /properties/{id}/collections`."""

    class Meta:
        model = CollectionMembership
        fields = [
            "id",
            "collection",
            "property",
            "sort_order",
            "featured_until",
            "description",
        ]
        read_only_fields = ["id", "property"]


class CollectionMembershipWriteSerializer(serializers.Serializer[None]):
    """Write shape for the `PUT /properties/{id}/collections` body.

    Accepts a collection reference as either numeric pk or slug.
    """

    collection = serializers.CharField()
    sort_order = serializers.IntegerField(required=False, default=0, min_value=0)
    featured_until = serializers.DateField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
