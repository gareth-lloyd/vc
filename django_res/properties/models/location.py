from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models.base import AuditedModel
from properties.timezones import validate_iana_timezone


class PropertyLocation(AuditedModel):
    """Postal address and geo coordinates for a `Property`."""

    property = models.OneToOneField(
        "properties.Property",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="location",
    )
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    address_line_3 = models.CharField(max_length=255, blank=True)
    post_code = models.CharField(max_length=32, blank=True)
    locality_town = models.CharField(max_length=128, blank=True)
    locality_region = models.CharField(max_length=128, blank=True)
    country = models.ForeignKey(
        "properties.Country",
        on_delete=models.PROTECT,
        related_name="property_locations",
    )
    # Range validators mirror the serializer's bounds at the model layer (like
    # `timezone` below), so admin edits and other non-API writers can't store a
    # coordinate outside the valid geographic range. `max_digits=9` alone only
    # caps magnitude at ±999.999999.
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    # IANA timezone name, a geographic fact of the place (follows `country`).
    # Default UTC is the safe fallback before the country-derived value is set
    # by the loader / factory / backfill; ops corrects outliers in the admin.
    timezone = models.CharField(
        max_length=64,
        default="UTC",
        validators=[validate_iana_timezone],
    )

    def __str__(self) -> str:
        return f"Location for property #{self.property_id}"
