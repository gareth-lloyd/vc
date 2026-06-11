"""Request shape for `POST /quotations:search-options`."""

from __future__ import annotations

from rest_framework import serializers

# Deliberately wider than the enquiry's flexibility_days cap (3): intake
# records a tight ± spread, but the quote-builder search may sweep a
# multi-week window ("any week in June") around the preferred stay. ±21 days
# bounds the sweep at three weeks either side — wide enough for a month-long
# window, small enough to keep the block list scannable.
SEARCH_FLEX_MAX = 21


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
