"""Pricing helper endpoints — quote + quote-bulk."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import DomainError
from pricing.models import Currency
from pricing.serializers import (
    PricingQuoteBulkRequestSerializer,
    PricingQuoteRequestSerializer,
)
from pricing.services import PricingEngine
from properties.models import Property

if TYPE_CHECKING:
    from rest_framework.request import Request


def _run_quote(*, property: Property, currency: Currency, data: dict[str, Any]) -> dict[str, Any]:
    quote = PricingEngine.quote(
        property=property,
        date_from=data["date_from"],
        date_to=data["date_to"],
        party=data["adults"] + data.get("children", 0),
        currency=currency,
        discount_code=data.get("discount_code") or None,
        opt_in_extras=list(data.get("opt_in_extras") or []),
    )
    return quote.breakdown


class PricingQuoteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = PricingQuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        property_obj = get_object_or_404(Property, pk=data["property_id"])
        currency = get_object_or_404(Currency, code=data["currency"].upper())
        breakdown = _run_quote(property=property_obj, currency=currency, data=data)
        return Response(breakdown)


class PricingQuoteBulkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = PricingQuoteBulkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        currency = get_object_or_404(Currency, code=data["currency"].upper())
        # Batch-load every requested property (with its images) up front so the
        # per-entry hero_image_url lookup doesn't fire a query per row.
        property_ids = [entry["property_id"] for entry in data["requests"]]
        properties_by_id = {
            p.pk: p for p in Property.objects.filter(pk__in=property_ids).prefetch_related("images")
        }
        quotes: list[dict[str, Any]] = []
        for entry in data["requests"]:
            property_obj = properties_by_id.get(entry["property_id"])
            if property_obj is None:
                quotes.append({"property_id": entry["property_id"], "available": False})
                continue
            try:
                breakdown = _run_quote(
                    property=property_obj,
                    currency=currency,
                    data=entry,
                )
            except DomainError as exc:
                quotes.append(
                    {
                        "property_id": entry["property_id"],
                        "available": False,
                        "error_code": getattr(exc, "code", "domain_error"),
                        "error_detail": str(exc),
                    }
                )
                continue
            quotes.append(
                {
                    "property_id": entry["property_id"],
                    "available": True,
                    "hero_image_url": property_obj.hero_image_url(),
                    **breakdown,
                }
            )
        return Response({"quotes": quotes})
