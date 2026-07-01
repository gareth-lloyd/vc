"""Views for Seasons (RatePlan), Rate Periods, and Rate Rules (GAP-056)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import IsReservationsWriter
from pricing.models import Currency, RateCard, RatePeriod, RatePlan, RateRule
from pricing.serializers import (
    RatePeriodSerializer,
    RatePlanDetailSerializer,
    RatePlanSerializer,
    RateRuleSerializer,
)
from pricing.services.carryover import RateCarryoverService
from properties.models import Property

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


def _transitional_card_for_plan(plan: RatePlan) -> RateCard:
    """Return a card to satisfy the still-non-null `RateRule.card` FK (GAP-056).

    The API is period-native, but `RateCard` survives as a nullable-in-spirit
    transitional column until Unit 9 drops it. Period-native band writes attach
    to any existing card on the plan (the migrated/loaded one), or a single
    synthesized card when the plan has none. The card-scoped `raterule_no_overlap`
    EXCLUDE stays satisfied: periods are date-disjoint and bands are
    party-disjoint per period, so the union on one card is (date x party)-disjoint.
    """
    card = RateCard.objects.filter(plan=plan).order_by("pk").first()
    if card is None:
        card = RateCard.objects.create(plan=plan, name=plan.name or "Rates")
    return card


class PropertySeasonListCreateView(generics.ListCreateAPIView):
    """`GET / POST /properties/{id}/seasons`."""

    permission_classes = [IsReservationsWriter]

    def get_serializer_class(self) -> type[Any]:
        return RatePlanSerializer

    def get_queryset(self) -> QuerySet[RatePlan]:
        return RatePlan.objects.filter(property_id=self.kwargs["property_id"]).select_related(
            "currency"
        )

    def perform_create(self, serializer: Any) -> None:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        serializer.save(property=property_obj)


class SeasonDetailView(generics.RetrieveUpdateDestroyAPIView):
    """`GET / PATCH / DELETE /seasons/{id}` — flat alias."""

    queryset = RatePlan.objects.select_related("currency").prefetch_related("periods__rules")
    permission_classes = [IsReservationsWriter]

    def get_serializer_class(self) -> type[Any]:
        if self.request.method in {"GET"}:
            return RatePlanDetailSerializer
        return RatePlanSerializer


class SeasonDuplicateView(APIView):
    permission_classes = [IsReservationsWriter]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        original = get_object_or_404(RatePlan, pk=self.kwargs["pk"])
        with transaction.atomic():
            original_pk = original.pk
            clone = RatePlan.objects.get(pk=original_pk)
            clone.pk = None
            clone.name = f"{original.name} (copy)"
            clone.save()
            # GAP-056: clone the period/band grid onto the new plan. Each cloned
            # rule attaches to the clone's transitional card (its dates come from
            # the cloned period) — never the source plan's card/period.
            clone_card = _transitional_card_for_plan(clone)
            for period in RatePeriod.objects.filter(plan_id=original_pk):
                source_period_pk = period.pk
                period_clone = RatePeriod.objects.get(pk=source_period_pk)
                period_clone.pk = None
                period_clone.plan = clone
                period_clone.save()
                for rule in RateRule.objects.filter(period_id=source_period_pk):
                    rule.pk = None
                    rule.period = period_clone
                    rule.card = clone_card
                    rule.save()
        return Response(
            RatePlanDetailSerializer(clone).data,
            status=status.HTTP_201_CREATED,
        )


class PropertySeasonCarryForwardView(APIView):
    """`POST /properties/{id}/seasons:carry-forward` — promote a projection.

    Materialises editable rate rows for a future year from the most recent prior
    year (the demoted carryover verb). Lazy projection already quotes that year
    without any rows; this is for when staff want to hand-tune or confirm. The
    operation is idempotent per (property, currency, target_year).

    Body: `{"currency": "GBP", "target_year": 2028, "uplift_pct": "0"}` —
    `uplift_pct` optional (defaults to a verbatim carry-over).
    """

    permission_classes = [IsReservationsWriter]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        data = request.data if isinstance(request.data, dict) else {}

        code = data.get("currency")
        target_year = data.get("target_year")
        if not code or target_year is None:
            return Response(
                {"detail": "currency and target_year are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            target_year_int = int(target_year)
            uplift = Decimal(str(data.get("uplift_pct", "0"))) / Decimal("100")
        except (ValueError, TypeError, InvalidOperation):
            return Response(
                {"detail": "target_year and uplift_pct must be numeric"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Bound the year to a sane window. Without this, a value like 0 or 10000
        # reaches `date(target_year, 1, 1)` in the service and raises an uncaught
        # ValueError (HTTP 500); anything outside a few decades is operator error.
        this_year = date.today().year
        if not (this_year <= target_year_int <= this_year + 20):
            return Response(
                {"detail": f"target_year must be between {this_year} and {this_year + 20}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        currency = get_object_or_404(Currency, code=code)

        # NoRateAvailable (no prior year to carry from) propagates to the
        # canonical domain-error handler as a 409.
        plan = RateCarryoverService.materialise(
            property_obj,
            target_year=target_year_int,
            currency=currency,
            uplift=uplift,
        )
        return Response(
            RatePlanDetailSerializer(plan).data,
            status=status.HTTP_201_CREATED,
        )


class SeasonRatePeriodListCreateView(generics.ListCreateAPIView):
    """`GET / POST /seasons/{id}/rate-periods`."""

    serializer_class = RatePeriodSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[RatePeriod]:
        return RatePeriod.objects.filter(plan_id=self.kwargs["season_id"]).prefetch_related("rules")

    def perform_create(self, serializer: Any) -> None:
        plan = get_object_or_404(RatePlan, pk=self.kwargs["season_id"])
        serializer.save(plan=plan)


class RatePeriodDetailView(generics.RetrieveUpdateDestroyAPIView):
    """`GET / PATCH / DELETE /periods/{id}` — flat alias."""

    queryset = RatePeriod.objects.all().prefetch_related("rules")
    serializer_class = RatePeriodSerializer
    permission_classes = [IsReservationsWriter]

    def perform_update(self, serializer: Any) -> None:
        """Repoint the period's bands when its dates move (GAP-056 transitional).

        `RateRule.date_from/date_to` are still non-null columns (dropped Unit 9)
        and the card-scoped overlap EXCLUDE reads them, so a period date-edit must
        drag its bands' dates along or the two axes drift. Bulk `.update()` is
        safe: `RateRule` dates are no longer audit-tracked (they're period-level
        facts now), and the moved band set stays date-disjoint from other periods'
        bands (the serializer already enforced period date-disjointness).
        """
        instance = serializer.instance
        old_dates = (instance.date_from, instance.date_to)
        period = serializer.save()
        if (period.date_from, period.date_to) != old_dates:
            period.rules.update(date_from=period.date_from, date_to=period.date_to)


class RatePeriodRuleListCreateView(generics.ListCreateAPIView):
    """`GET / POST /periods/{id}/rules` — partyxprice bands under a period."""

    serializer_class = RateRuleSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[RateRule]:
        return RateRule.objects.filter(period_id=self.kwargs["period_id"])

    def perform_create(self, serializer: Any) -> None:
        period = get_object_or_404(RatePeriod, pk=self.kwargs["period_id"])
        # Dates are inherited from the period; the transitional card FK is filled
        # server-side (GAP-056 — both drop out in Unit 9).
        serializer.save(
            period=period,
            card=_transitional_card_for_plan(period.plan),
            date_from=period.date_from,
            date_to=period.date_to,
        )


class RateRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """`GET / PATCH / DELETE /rules/{id}` — flat alias (party/price only)."""

    queryset = RateRule.objects.all()
    serializer_class = RateRuleSerializer
    permission_classes = [IsReservationsWriter]
