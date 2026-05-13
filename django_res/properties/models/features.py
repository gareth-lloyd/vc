from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel, TimestampedModel
from properties.enums import FeatureServiceType


class FeatureCategory(TimestampedModel):
    """Top-level grouping of features (e.g. "Outdoor", "Kitchen")."""

    name = models.CharField(max_length=128, unique=True)
    slug = models.SlugField(max_length=128, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=128, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "feature categories"

    def __str__(self) -> str:
        return self.name


class Feature(TimestampedModel):
    """A single feature / amenity / included service / paid add-on."""

    category = models.ForeignKey(
        FeatureCategory,
        on_delete=models.PROTECT,
        related_name="features",
    )
    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=128, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=128, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    service_type = models.CharField(
        max_length=24,
        choices=FeatureServiceType.choices,
        default=FeatureServiceType.AMENITY,
    )
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["category_id", "sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Collection(AuditedModel):
    """A curated marketing collection of properties."""

    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=128, unique=True)
    description = models.TextField(blank=True)
    cover_image = models.ImageField(
        upload_to="collections/%Y/%m/",
        blank=True,
        null=True,
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class CollectionMembership(TimestampedModel):
    """Through model linking `Collection` to `Property` with curation metadata."""

    collection = models.ForeignKey(
        Collection,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="collection_memberships",
    )
    sort_order = models.PositiveIntegerField(default=0)
    featured_until = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "property"],
                name="unique_collection_property",
            ),
        ]
        ordering = ["collection_id", "sort_order"]

    def __str__(self) -> str:
        return f"{self.property_id} in {self.collection_id}"
