from __future__ import annotations

from django.db import models

from core.models.base import TimestampedModel


class Country(TimestampedModel):
    """ISO-coded country lookup. Curated by staff."""

    name = models.CharField(max_length=128)
    iso2 = models.CharField(max_length=2, unique=True)
    iso3 = models.CharField(max_length=3, unique=True)
    dial_code = models.CharField(max_length=8, blank=True)
    default_tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "countries"

    def __str__(self) -> str:
        return self.name


class Region(TimestampedModel):
    """A region inside a country (e.g. Cornwall, Tuscany)."""

    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="regions",
    )
    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=128)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["country", "slug"],
                name="unique_region_slug_per_country",
            ),
        ]
        ordering = ["country__name", "sort_order", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.country.iso2})"


class NearbyPlaceType(TimestampedModel):
    """A category of nearby place (beach, restaurant, ski lift…)."""

    name = models.CharField(max_length=128, unique=True)
    icon = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PropertyNearbyPlace(TimestampedModel):
    """A named nearby point of interest attached to a property."""

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="nearby_places",
    )
    place_type = models.ForeignKey(
        NearbyPlaceType,
        on_delete=models.PROTECT,
        related_name="placements",
    )
    name = models.CharField(max_length=255)
    distance_km = models.DecimalField(max_digits=6, decimal_places=2)
    notes = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["property_id", "sort_order", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.distance_km} km)"
