"""Serializers for `RatePlan` (per-currency rate sheet), `RatePeriod`, and `RateBand`.

GAP-056: the honest grid is `RatePlan → RatePeriod (dates) → RateBand (party
band)`. `RateBand` carries no `date_from/date_to` — those live on its parent
`RatePeriod`; the band is a partyxprice row that inherits the period's dates.
`RateCard` is gone (dropped in Unit 9).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.db import models
from django.utils import timezone
from rest_framework import serializers

from pricing.models import RateBand, RatePeriod, RatePlan
from properties.models import Property

# Record-level lock message shared by the serializers and the destroy views.
HISTORICAL_LOCKED_MESSAGE = (
    "This rate period has already ended, so its rates are locked and read-only."
)

# Refusal shown when someone tries to *create* a period that has already ended.
HISTORICAL_CREATE_MESSAGE = (
    "You can only add a rate period that is current or upcoming — this one has already ended."
)


def guard_period_editable(period: RatePeriod | None) -> None:
    """Raise if ``period`` has fully elapsed (its rates are frozen)."""
    if period is not None and period.is_historical:
        raise serializers.ValidationError(HISTORICAL_LOCKED_MESSAGE)


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
    """A partyxprice band. Dates are inherited from its `period` (GAP-056).

    Q-018: `nightly`/`weekly` are the **base** prices; a reduction (percent XOR
    fixed new amounts) is stored alongside and the quoted `effective_*` prices
    are derived, never written.
    """

    period: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(read_only=True)
    # Model properties, so declared explicitly; mirror the base fields' shape
    # (DRF renders them as the same "0.00" strings the FE money schemas expect).
    effective_nightly = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, allow_null=True
    )
    effective_weekly = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, allow_null=True
    )

    class Meta:
        model = RateBand
        fields = [
            "id",
            "period",
            "min_party",
            "max_party",
            "nightly",
            "weekly",
            "reduction_percent",
            "reduced_nightly",
            "reduced_weekly",
            "reduced_at",
            "reduction_reason",
            "effective_nightly",
            "effective_weekly",
            "is_poa",
            "is_locked",
            "is_approved",
            "notes",
        ]
        read_only_fields = ["id", "period", "effective_nightly", "effective_weekly"]

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

        self._validate_reduction(attrs, effective)

        period = self._resolve_period()
        guard_period_editable(period)
        if period is not None and self.instance is None and not period.plan.prices_by_occupancy:
            if period.bands.exists():
                raise serializers.ValidationError(
                    {
                        "prices_by_occupancy": (
                            "This plan uses a single flat rate. Switch it to occupancy "
                            "pricing to add party-size bands."
                        ),
                    },
                )
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

    def _validate_reduction(self, attrs: dict[str, Any], effective: Callable[[str], Any]) -> None:
        """Q-018: mirror the reduction CheckConstraints as friendly 400s.

        Works on the merged (stored + incoming) values, so both a bad reduction
        write and a base edit that clashes with a stored reduction (review M2 —
        the MatrixCell inline editors PATCH only `nightly`/`weekly`) land here
        rather than as an `IntegrityError` 500. Every error is keyed on a field
        the client actually sent, so form UIs can attach it to a live input.
        """
        nightly, weekly, is_poa = effective("nightly"), effective("weekly"), effective("is_poa")
        percent = effective("reduction_percent")
        reduced_nightly = effective("reduced_nightly")
        reduced_weekly = effective("reduced_weekly")
        has_fixed = reduced_nightly is not None or reduced_weekly is not None
        has_reduction = percent is not None or has_fixed

        def sent(*fields: str) -> str:
            """The first of `fields` present in the request, else the first."""
            return next((f for f in fields if f in attrs), fields[0])

        if has_reduction and is_poa:
            raise serializers.ValidationError(
                {
                    sent("is_poa", "reduction_percent", "reduced_nightly", "reduced_weekly"): (
                        "A POA band has no price, so it cannot carry a reduction."
                    ),
                },
            )
        if percent is not None and has_fixed:
            raise serializers.ValidationError(
                {
                    sent("reduction_percent", "reduced_nightly", "reduced_weekly"): (
                        "Use a percentage reduction OR fixed reduced amounts, not both."
                    ),
                },
            )
        if percent is not None and not (0 < percent < 100):
            raise serializers.ValidationError(
                {"reduction_percent": "The reduction must be between 0 and 100% (exclusive)."},
            )

        pairs = (
            ("reduced_nightly", "nightly", reduced_nightly, nightly),
            ("reduced_weekly", "weekly", reduced_weekly, weekly),
        )
        for reduced_field, base_field, reduced_value, base_value in pairs:
            if reduced_value is None:
                continue
            if base_value is None:
                if base_field in attrs and reduced_field not in attrs:
                    # The client is clearing the base under a stored reduction.
                    raise serializers.ValidationError(
                        {
                            base_field: (
                                f"This band still has a reduced {base_field} "
                                f"({reduced_value}) — clear the reduction before "
                                f"removing the {base_field} price."
                            ),
                        },
                    )
                raise serializers.ValidationError(
                    {reduced_field: f"This band has no {base_field} price to reduce."},
                )
            if not (0 < reduced_value < base_value):
                # A base edit clashing with a stored reduction surfaces on the
                # base input (M2); a bad reduction write on the reduced input.
                key = (
                    base_field
                    if (base_field in attrs and reduced_field not in attrs)
                    else reduced_field
                )
                raise serializers.ValidationError(
                    {
                        key: (
                            f"The reduced {base_field} ({reduced_value}) must be above zero "
                            f"and below the base {base_field} ({base_value}). Adjust the "
                            "price or clear the reduction first."
                        ),
                    },
                )

        # Decision 6b: quoting prefers the nightly price, so a fixed reduction
        # must cover EVERY base price the band carries — a partial pair would
        # be a silent no-op (or an accidental cut). Checked after the per-pair
        # errors so "nothing to reduce" wins on the field the client sent.
        if has_fixed:
            for reduced_field, base_field, reduced_value, base_value in pairs:
                if reduced_value is None and base_value is not None:
                    raise serializers.ValidationError(
                        {
                            reduced_field: (
                                "A fixed reduction must cover every base price on this "
                                f"band — set a reduced {base_field} too, or clear both "
                                "reduced amounts to remove the reduction."
                            ),
                        },
                    )

        if not has_reduction:
            # Explicitly-sent metadata with nothing to annotate is a mistake —
            # reject it rather than silently dropping the client's values.
            if attrs.get("reduced_at") is not None or attrs.get("reduction_reason"):
                key = "reduced_at" if attrs.get("reduced_at") is not None else "reduction_reason"
                raise serializers.ValidationError(
                    {key: "There is no reduction on this band to annotate — set one first."},
                )
            # No reduction left → no stale metadata: clear the audit companions.
            if effective("reduced_at") is not None or effective("reduction_reason"):
                attrs["reduced_at"] = None
                attrs["reduction_reason"] = ""

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
        plan_id = getattr(view, "kwargs", {}).get("plan_id")
        if plan_id is None:
            return None
        return RatePlan.objects.filter(pk=plan_id).first()

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

        # A period whose window has fully elapsed is locked: reject any edit to
        # the stored row.
        guard_period_editable(self.instance)

        date_from, date_to = effective("date_from"), effective("date_to")
        if date_from is not None and date_to is not None and date_from > date_to:
            raise serializers.ValidationError(
                {"date_to": "date_to must be on or after date_from."},
            )

        # ...and you can't manufacture a fresh one that has already ended — it
        # would be born locked (unremovable, no bands). Only current/upcoming
        # periods can be created via the API (loaders backfill via the ORM).
        if self.instance is None and date_to is not None and date_to < timezone.localdate():
            raise serializers.ValidationError({"date_to": HISTORICAL_CREATE_MESSAGE})

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
            "prices_by_occupancy",
            "fallback_nightly",
            "effective_from",
            "effective_to",
            "is_active",
            "notes",
        ]
        read_only_fields = ["id"]

    def validate_prices_by_occupancy(self, value: bool) -> bool:
        """Occupancy → flat is only safe once every period holds a single band.

        Collapsing to flat is lossless only when there is nothing to collapse:
        a period with several party bands has no single price to keep, so we
        make the operator reduce it first rather than silently dropping bands.
        Flat → occupancy (``value`` True) is always allowed.
        """
        if value or self.instance is None:
            return value
        multi = self.instance.periods.annotate(n=models.Count("bands")).filter(n__gt=1).exists()
        if multi:
            raise serializers.ValidationError(
                "Reduce each period to a single band before switching to flat pricing.",
            )
        return value


class RatePlanDetailSerializer(RatePlanSerializer):
    """Full detail — inlines `periods` with their bands."""

    periods = RatePeriodSerializer(many=True, read_only=True)

    class Meta(RatePlanSerializer.Meta):
        fields = [*RatePlanSerializer.Meta.fields, "periods"]
        read_only_fields = [*RatePlanSerializer.Meta.read_only_fields, "periods"]


class RatePlanDuplicateSerializer(serializers.Serializer[None]):
    """Input for `POST /rate-plans/{id}:duplicate` (SMELL-009).

    Retrying UIs send a key; a repeat POST with the same key returns the
    original clone (FG-010). Absent, blank, and explicit-null all mean
    "no idempotency requested" — the bodyless FE call keeps working.
    `max_length=64` matches the model column.
    """

    idempotency_key = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default="", max_length=64
    )
