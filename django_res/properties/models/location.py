from __future__ import annotations

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
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
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
