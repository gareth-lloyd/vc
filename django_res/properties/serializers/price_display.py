"""Website price-display serializer.

The model does not yet exist as a dedicated row — we project a stable shape
from `PropertyFinance` + `PropertySettings`. This stub keeps the API contract
green; the FE can drive the field set forward.
"""

from __future__ import annotations

from rest_framework import serializers


class PropertyPriceDisplaySerializer(serializers.Serializer[None]):
    poa = serializers.BooleanField(required=False, default=False)
    show_min = serializers.BooleanField(required=False, default=True)
    show_max = serializers.BooleanField(required=False, default=False)
    symbol_position = serializers.ChoiceField(
        choices=["leading", "trailing"],
        required=False,
        default="leading",
    )
