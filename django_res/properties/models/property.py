from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.db import models

from core.models.base import AuditedModel, TimestampedModel
from properties.enums import PropertyChannel, PropertyStatus

if TYPE_CHECKING:
    from properties.models.images import PropertyImage


class PropertyCategory(TimestampedModel):
    """Editable lookup of property kinds (villa, apartment, chalet…)."""

    name = models.CharField(max_length=128, unique=True)
    slug = models.SlugField(max_length=128, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "property categories"

    def __str__(self) -> str:
        return self.name


class PropertyGroup(AuditedModel):
    """Organisational grouping of properties (e.g. a brand sub-portfolio)."""

    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Property(AuditedModel):
    """Catalogue entry for a bookable villa / apartment / chalet."""

    name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    licence_number = models.CharField(max_length=128, blank=True)
    status = models.CharField(
        max_length=16,
        choices=PropertyStatus.choices,
        default=PropertyStatus.DRAFT,
    )
    channel = models.CharField(
        max_length=16,
        choices=PropertyChannel.choices,
        default=PropertyChannel.DIRECT,
    )
    category = models.ForeignKey(
        PropertyCategory,
        on_delete=models.PROTECT,
        related_name="properties",
    )
    group = models.ForeignKey(
        PropertyGroup,
        on_delete=models.PROTECT,
        related_name="properties",
    )
    region = models.ForeignKey(
        "properties.Region",
        on_delete=models.PROTECT,
        related_name="properties",
    )
    features = models.ManyToManyField(
        "properties.Feature",
        blank=True,
        related_name="properties",
    )
    collections = models.ManyToManyField(
        "properties.Collection",
        through="properties.CollectionMembership",
        related_name="properties",
        blank=True,
    )
    contacts = models.ManyToManyField(
        "accounts.Contact",
        through="properties.PropertyContactAssignment",
        related_name="properties",
        blank=True,
    )
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["region", "status"]),
            models.Index(fields=["group"]),
            models.Index(fields=["legacy_id"]),
        ]
        verbose_name_plural = "properties"

    def __str__(self) -> str:
        return self.display_name or self.name

    def balance_due_at(self, date_from: date | None) -> date | None:
        """Derive balance-due date from the property's effective payment schedule."""
        if date_from is None:
            return None
        finance = getattr(self, "finance", None)
        if finance is None:
            return None
        schedule = finance.effective_payment_schedule()
        days_before = schedule.get("days_balance_due_before_arrival")
        if days_before is None:
            return None
        return date_from - timedelta(days=int(days_before))

    def hero_image(self) -> PropertyImage | None:
        """Return the property's active hero image, if any."""
        from properties.enums import ImageKind

        return self.images.filter(kind=ImageKind.HERO, is_active=True).first()
