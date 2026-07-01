"""Serializers for `RatePlan` (Season), `RatePeriod`, and `RateBand`.

GAP-056: the honest grid is `RatePlan → RatePeriod (dates) → RateBand (party
band)`. `RateBand` carries no `date_from/date_to` — those live on its parent
`RatePeriod`; the band is a partyxprice row that inherits the period's dates.
`RateCard` is gone (dropped in Unit 9).
"""

from __future__ import annotations

from typing import Any

from django.db import models
from rest_framework import serializers

from pricing.models import RateBand, RatePeriod, RatePlan
from properties.models import Property


def _max_occupancy(plan: RatePlan) -> int | None:
    """The property's occupancy cap (`PropertyCapacity.guests`) for coverage.

    Defensive: a property with no `capacity` row (hand-built test fixtures) or a
    zero cap yields `None`, which disables the party-gap coverage check rather
    than raising — the engine's `NoRateAvailable` is the runtime backstop.
    """
    capacity = getattr(plan.property, "capacity", None)
    guests = getattr(capacity, "guests", None)
    if not guests or guests < 1:
        return None
    return int(guests)


def _coverage_gaps(bands: list[RateBand], cap: int | None) -> list[list[int]]:
    """Uncovered `[low, high]` party sub-ranges of `1..cap` across `bands`.

    Bands are inclusive `min_party..max_party`. Returns the party counts no band
    prices — POA is an explicit band, never a gap. Empty list = full coverage.
    """
    if cap is None:
        return []
    covered: set[int] = set()
    for band in bands:
        covered.update(range(band.min_party, min(band.max_party, cap) + 1))
    gaps: list[list[int]] = []
    run_start: int | None = None
    for party in range(1, cap + 1):
        if party in covered:
            if run_start is not None:
                gaps.append([run_start, party - 1])
                run_start = None
        elif run_start is None:
            run_start = party
    if run_start is not None:
        gaps.append([run_start, cap])
    return gaps


class RateBandSerializer(serializers.ModelSerializer[RateBand]):
    """A partyxprice band. Dates are inherited from its `period` (GAP-056)."""

    period: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = RateBand
        fields = [
            "id",
            "period",
            "min_party",
            "max_party",
            "nightly",
            "weekly",
            "is_poa",
            "is_locked",
            "is_approved",
            "notes",
        ]
        read_only_fields = ["id", "period"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Mirror the band's DB constraints as 400s, plus party-overlap.

        Dates live on the period now, so this validates only the party band and
        the price/POA rules. Overlap is checked **within the period** on the
        party axis (two bands on one period must not share a party count). A
        missing key falls back to the stored instance (PATCH) or the model
        default (create).
        """

        def effective(field: str) -> Any:
            if field in attrs:
                return attrs[field]
            if self.instance is not None:
                return getattr(self.instance, field)
            model_field = RateBand._meta.get_field(field)
            assert isinstance(model_field, models.Field)  # only concrete columns queried
            return model_field.get_default() if model_field.has_default() else None

        min_party, max_party = effective("min_party"), effective("max_party")
        if min_party is not None and max_party is not None and min_party > max_party:
            raise serializers.ValidationError(
                {"max_party": "max_party must be greater than or equal to min_party."},
            )

        nightly, weekly, is_poa = effective("nightly"), effective("weekly"), effective("is_poa")
        has_price = nightly is not None or weekly is not None
        if is_poa and has_price:
            raise serializers.ValidationError(
                {"is_poa": "A POA rule cannot also carry a nightly or weekly price."},
            )
        if not is_poa and not has_price:
            raise serializers.ValidationError(
                {"nightly": "Set a nightly or weekly price, or mark the rule POA."},
            )

        period = self._resolve_period()
        if period is not None and None not in (min_party, max_party):
            overlapping = RateBand.objects.filter(
                period=period,
                min_party__lte=max_party,
                max_party__gte=min_party,
            )
            if self.instance is not None:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            clash = overlapping.first()
            if clash is not None:
                raise serializers.ValidationError(
                    {
                        "min_party": (
                            "Party size overlaps an existing band in this period "
                            f"(party {clash.min_party}-{clash.max_party}). "
                            "Bands on one period must cover disjoint party ranges."
                        ),
                    },
                )
        return attrs

    def _resolve_period(self) -> RatePeriod | None:
        """The period comes from the stored row (PATCH) or the nested-create URL."""
        if self.instance is not None:
            return self.instance.period
        view = self.context.get("view")
        period_id = getattr(view, "kwargs", {}).get("period_id")
        if period_id is None:
            return None
        return RatePeriod.objects.filter(pk=period_id).first()


class RatePeriodSerializer(serializers.ModelSerializer[RatePeriod]):
    """A disjoint date window on a plan; owns the dates its bands inherit."""

    plan = serializers.PrimaryKeyRelatedField(
        queryset=RatePlan.objects.all(),
        required=False,
    )
    bands = RateBandSerializer(many=True, read_only=True)
    coverage_gaps = serializers.SerializerMethodField()

    class Meta:
        model = RatePeriod
        fields = [
            "id",
            "plan",
            "name",
            "date_from",
            "date_to",
            "min_nights",
            "max_nights",
            "is_active",
            "bands",
            "coverage_gaps",
        ]
        read_only_fields = ["id", "bands", "coverage_gaps"]

    def get_coverage_gaps(self, obj: RatePeriod) -> list[list[int]]:
        """Uncovered `1..max_occupancy` party ranges — the editor pre-warns on these."""
        cap = _max_occupancy(obj.plan)
        return _coverage_gaps(list(obj.bands.all()), cap)

    def _resolve_plan(self, attrs: dict[str, Any]) -> RatePlan | None:
        if attrs.get("plan") is not None:
            return attrs["plan"]
        if self.instance is not None:
            return self.instance.plan
        view = self.context.get("view")
        season_id = getattr(view, "kwargs", {}).get("season_id")
        if season_id is None:
            return None
        return RatePlan.objects.filter(pk=season_id).first()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Inclusive dates, period date-disjointness, and activation coverage.

        - Dates are inclusive: `date_from == date_to` is a legal single-day period.
        - Periods on one plan must not overlap on the date axis (the Unit 9
          EXCLUDE enforced in the DB; here we surface it as a 400).
        - When the period is (or becomes) `is_active` **and already has bands**,
          reject a gap in `1..max_occupancy` (POA is an explicit band, not a gap).
          A fresh period with no bands is exempt — coverage is built incrementally.
        """

        def effective(field: str) -> Any:
            if field in attrs:
                return attrs[field]
            if self.instance is not None:
                return getattr(self.instance, field)
            model_field = RatePeriod._meta.get_field(field)
            assert isinstance(model_field, models.Field)
            return model_field.get_default() if model_field.has_default() else None

        date_from, date_to = effective("date_from"), effective("date_to")
        if date_from is not None and date_to is not None and date_from > date_to:
            raise serializers.ValidationError(
                {"date_to": "date_to must be on or after date_from."},
            )

        plan = self._resolve_plan(attrs)
        if plan is not None and None not in (date_from, date_to):
            overlapping = RatePeriod.objects.filter(
                plan=plan,
                date_from__lte=date_to,
                date_to__gte=date_from,
            )
            if self.instance is not None:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            clash = overlapping.first()
            if clash is not None:
                raise serializers.ValidationError(
                    {
                        "date_from": (
                            "Dates overlap an existing period "
                            f"({clash.date_from} to {clash.date_to}). "
                            "Date ranges are inclusive: start the next period the "
                            "day after the previous one ends."
                        ),
                    },
                )

        if effective("is_active") and self.instance is not None and plan is not None:
            bands = list(self.instance.bands.all())
            cap = _max_occupancy(plan)
            gaps = _coverage_gaps(bands, cap)
            if bands and gaps:
                raise serializers.ValidationError(
                    {
                        "is_active": (
                            f"An active period must price every party size 1..{cap}. "
                            f"Uncovered ranges: {gaps}. Add a band (POA counts) to "
                            "close the gap."
                        ),
                    },
                )
        return attrs


class RatePlanSerializer(serializers.ModelSerializer[RatePlan]):
    """Lighter list shape — no nested periods/rules."""

    property = serializers.PrimaryKeyRelatedField(
        queryset=Property.objects.all(),
        required=False,
    )
    currency_code = serializers.CharField(source="currency.code", read_only=True)

    class Meta:
        model = RatePlan
        fields = [
            "id",
            "property",
            "name",
            "currency",
            "currency_code",
            "price_basis",
            "fallback_nightly",
            "effective_from",
            "effective_to",
            "is_active",
            "notes",
        ]
        read_only_fields = ["id"]


class RatePlanDetailSerializer(RatePlanSerializer):
    """Full detail — inlines `periods` with their bands."""

    periods = RatePeriodSerializer(many=True, read_only=True)

    class Meta(RatePlanSerializer.Meta):
        fields = [*RatePlanSerializer.Meta.fields, "periods"]
        read_only_fields = [*RatePlanSerializer.Meta.read_only_fields, "periods"]
