"""Views for Rate Plans, Rate Periods, and Rate Bands (GAP-056)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import IsReservationsWriter
from core.idempotency import integrity_conflict_guard
from pricing.models import Currency, RateBand, RatePeriod, RatePlan
from pricing.serializers import (
    RateBandSerializer,
    RatePeriodSerializer,
    RatePlanDetailSerializer,
    RatePlanDuplicateSerializer,
    RatePlanSerializer,
)
from pricing.serializers.rate import guard_period_editable
from pricing.services.carryover import RateCarryoverService
from pricing.services.duplication import duplicate_rate_plan
from properties.models import Property

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


class PropertyRatePlanListCreateView(generics.ListCreateAPIView):
    """`GET / POST /properties/{id}/rate-plans`."""

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


class RatePlanDetailView(generics.RetrieveUpdateDestroyAPIView):
    """`GET / PATCH / DELETE /rate-plans/{id}` — flat alias."""

    # `periods__plan__property__capacity` feeds RatePeriodSerializer.coverage_gaps
    # (`_max_occupancy`) without an N+1 per period on the nested detail read.
    queryset = RatePlan.objects.select_related("currency").prefetch_related(
        "periods__bands", "periods__plan__property__capacity"
    )
    permission_classes = [IsReservationsWriter]

    def get_serializer_class(self) -> type[Any]:
        if self.request.method in {"GET"}:
            return RatePlanDetailSerializer
        return RatePlanSerializer


class RatePlanDuplicateView(APIView):
    """`POST /rate-plans/{id}:duplicate` — clone the plan + grid (SMELL-009)."""

    permission_classes = [IsReservationsWriter]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        original = get_object_or_404(RatePlan, pk=self.kwargs["pk"])
        serializer = RatePlanDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        idempotency_key = serializer.validated_data["idempotency_key"] or None
        # FG-010: the guard maps a racing loser's IntegrityError (from
        # `rateplan_idempotency_key_unique_per_property`) to a 409.
        with integrity_conflict_guard(
            idempotency_key,
            "A duplicate with this idempotency key already exists for this property.",
        ):
            clone = duplicate_rate_plan(original, idempotency_key=idempotency_key)
        return Response(
            RatePlanDetailSerializer(clone).data,
            status=status.HTTP_201_CREATED,
        )


class PropertyRatePlanCarryForwardView(APIView):
    """`POST /properties/{id}/rate-plans:carry-forward` — promote a projection.

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


class RatePlanRatePeriodListCreateView(generics.ListCreateAPIView):
    """`GET / POST /rate-plans/{id}/rate-periods`."""

    serializer_class = RatePeriodSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[RatePeriod]:
        # `plan__property__capacity` feeds coverage_gaps (`_max_occupancy`).
        return (
            RatePeriod.objects.filter(plan_id=self.kwargs["plan_id"])
            .select_related("plan__property__capacity")
            .prefetch_related("bands")
        )

    def perform_create(self, serializer: Any) -> None:
        plan = get_object_or_404(RatePlan, pk=self.kwargs["plan_id"])
        serializer.save(plan=plan)


class RatePeriodDetailView(generics.RetrieveUpdateDestroyAPIView):
    """`GET / PATCH / DELETE /periods/{id}` — flat alias."""

    queryset = RatePeriod.objects.select_related("plan__property__capacity").prefetch_related(
        "bands"
    )
    serializer_class = RatePeriodSerializer
    permission_classes = [IsReservationsWriter]
    # GAP-056: bands inherit their dates from the period (no per-rule date
    # columns), so a period date-edit needs no band repoint — the default
    # `perform_update` (a plain save) suffices.

    def perform_destroy(self, instance: RatePeriod) -> None:
        # A fully-elapsed period is a read-only record of what was charged.
        guard_period_editable(instance)
        instance.delete()


class RatePeriodBandListCreateView(generics.ListCreateAPIView):
    """`GET / POST /periods/{id}/bands` — partyxprice bands under a period."""

    serializer_class = RateBandSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[RateBand]:
        return RateBand.objects.filter(period_id=self.kwargs["period_id"])

    def perform_create(self, serializer: Any) -> None:
        # A band hangs off its period, which owns the date window (GAP-056).
        period = get_object_or_404(RatePeriod, pk=self.kwargs["period_id"])
        serializer.save(period=period)


class RateBandDetailView(generics.RetrieveUpdateDestroyAPIView):
    """`GET / PATCH / DELETE /bands/{id}` — flat alias (party/price only)."""

    queryset = RateBand.objects.select_related("period")
    serializer_class = RateBandSerializer
    permission_classes = [IsReservationsWriter]

    def perform_destroy(self, instance: RateBand) -> None:
        # Bands on a fully-elapsed period are locked along with the period.
        guard_period_editable(instance.period)
        instance.delete()
