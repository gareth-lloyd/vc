"""Serializer for `PropertyLocation` (postal address + geo coordinates)."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from properties.models import PropertyLocation
from properties.timezones import validate_iana_timezone


class PropertyLocationSerializer(serializers.ModelSerializer[PropertyLocation]):
    # `country` is a non-nullable FK; surface it as a writable pk. Latitude /
    # longitude are bounded to valid geographic ranges (the model's
    # max_digits=9 only caps magnitude at ±999.999999). `timezone` reuses the
    # shared IANA validator. Migrated rows are already within range (checked),
    # so these bounds don't break edits to existing addresses.
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-90"),
        max_value=Decimal("90"),
        allow_null=True,
        required=False,
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-180"),
        max_value=Decimal("180"),
        allow_null=True,
        required=False,
    )
    timezone = serializers.CharField(validators=[validate_iana_timezone], required=False)

    class Meta:
        model = PropertyLocation
        fields = [
            "property",
            "address_line_1",
            "address_line_2",
            "address_line_3",
            "post_code",
            "locality_town",
            "locality_region",
            "country",
            "latitude",
            "longitude",
            "timezone",
        ]
        read_only_fields = ["property"]
