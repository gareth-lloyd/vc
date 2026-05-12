"""Serializers for geo lookups (`Country`, `Region`, nearby place)."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import (
    Country,
    NearbyPlaceType,
    PropertyNearbyPlace,
    Region,
)


class CountrySerializer(serializers.ModelSerializer[Country]):
    class Meta:
        model = Country
        fields = [
            "id",
            "name",
            "iso2",
            "iso3",
            "dial_code",
            "default_tax_rate",
            "sort_order",
            "is_active",
        ]
        read_only_fields = ["id"]


class RegionSerializer(serializers.ModelSerializer[Region]):
    class Meta:
        model = Region
        fields = ["id", "country", "name", "slug", "sort_order", "is_active"]
        read_only_fields = ["id"]


class NearbyPlaceTypeSerializer(serializers.ModelSerializer[NearbyPlaceType]):
    class Meta:
        model = NearbyPlaceType
        fields = ["id", "name", "icon"]
        read_only_fields = ["id", "name", "icon"]


class PropertyNearbyPlaceSerializer(serializers.ModelSerializer[PropertyNearbyPlace]):
    class Meta:
        model = PropertyNearbyPlace
        fields = [
            "id",
            "property",
            "place_type",
            "name",
            "distance_km",
            "notes",
            "sort_order",
        ]
        read_only_fields = ["id", "property"]
