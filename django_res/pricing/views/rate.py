"""Views for Seasons (RatePlan), Rate Cards, and Rate Rules."""

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
from pricing.models import Currency, RateCard, RatePlan, RateRule
from pricing.serializers import (
    RateCardSerializer,
    RatePlanDetailSerializer,
    RatePlanSerializer,
    RateRuleSerializer,
)
from pricing.services.carryover import RateCarryoverService
from properties.models import Property

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


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

    queryset = RatePlan.objects.select_related("currency").prefetch_related("cards__rules")
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
            for card in RateCard.objects.filter(plan_id=original_pk):
                card_pk = card.pk
                card_clone = RateCard.objects.get(pk=card_pk)
                card_clone.pk = None
                card_clone.plan = clone
                card_clone.save()
                for rule in RateRule.objects.filter(card_id=card_pk):
                    rule.pk = None
                    rule.card = card_clone
                    # Drop the source period so the save() shim re-derives one on
                    # the CLONE's plan; else the clone's rules would point at the
                    # original plan's RatePeriod (cross-plan FK). (GAP-056)
                    rule.period = None
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


class SeasonRateCardListCreateView(generics.ListCreateAPIView):
    """`GET / POST /seasons/{id}/rate-cards`."""

    serializer_class = RateCardSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[RateCard]:
        return RateCard.objects.filter(plan_id=self.kwargs["season_id"]).prefetch_related("rules")

    def perform_create(self, serializer: Any) -> None:
        plan = get_object_or_404(RatePlan, pk=self.kwargs["season_id"])
        serializer.save(plan=plan)


class RateCardDetailView(generics.RetrieveUpdateDestroyAPIView):
    """`GET / PATCH / DELETE /rate-cards/{id}` — flat alias."""

    queryset = RateCard.objects.all().prefetch_related("rules")
    serializer_class = RateCardSerializer
    permission_classes = [IsReservationsWriter]


class RateCardDuplicateView(APIView):
    permission_classes = [IsReservationsWriter]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        original = get_object_or_404(RateCard, pk=self.kwargs["pk"])
        with transaction.atomic():
            original_pk = original.pk
            clone = RateCard.objects.get(pk=original_pk)
            clone.pk = None
            clone.name = f"{original.name} (copy)"
            target_plan = (
                request.data.get("target_plan_id") if isinstance(request.data, dict) else None
            )
            if target_plan:
                clone.plan_id = int(target_plan)
            clone.save()
            for rule in RateRule.objects.filter(card_id=original_pk):
                rule.pk = None
                rule.card = clone
                # Re-derive the period on the clone's plan (may be a different
                # plan when target_plan_id is set) — see SeasonDuplicateView. (GAP-056)
                rule.period = None
                rule.save()
        return Response(
            RateCardSerializer(clone).data,
            status=status.HTTP_201_CREATED,
        )


class RateCardRuleListCreateView(generics.ListCreateAPIView):
    """`GET / POST /rate-cards/{id}/rules`."""

    serializer_class = RateRuleSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[RateRule]:
        return RateRule.objects.filter(card_id=self.kwargs["rate_card_id"])

    def perform_create(self, serializer: Any) -> None:
        card = get_object_or_404(RateCard, pk=self.kwargs["rate_card_id"])
        serializer.save(card=card)


class RateRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """`GET / PATCH / DELETE /rules/{id}` — flat alias."""

    queryset = RateRule.objects.all()
    serializer_class = RateRuleSerializer
    permission_classes = [IsReservationsWriter]
