"""Request shape for `POST /quotations:search-options`."""

from __future__ import annotations

from rest_framework import serializers

# The enquiry's flexibility_days is capped at 3; the search window honours
# the same bound so the two never drift apart.
SEARCH_FLEX_MAX = 3


class _StayOptionsRequestEntrySerializer(serializers.Serializer[None]):
    property_id = serializers.IntegerField(min_value=1)
    # The client's PREFERRED dates — the window is derived server-side as
    # preferred ± flex_days.
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    adults = serializers.IntegerField(min_value=1)
    children = serializers.IntegerField(required=False, default=0, min_value=0)


class QuoteSearchOptionsRequestSerializer(serializers.Serializer[None]):
    """Body for `POST /quotations:search-options`."""

    flex_days = serializers.IntegerField(
        required=False, default=0, min_value=0, max_value=SEARCH_FLEX_MAX
    )
    # Optional (GAP-014) — omitted means "price in the rate plan's own
    # currency", mirroring /pricing:quote-bulk.
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True, default="")
    requests = _StayOptionsRequestEntrySerializer(many=True, allow_empty=False)
