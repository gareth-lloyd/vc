"""Pricing helper endpoints — quote + quote-bulk."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import IsStaff
from core.exceptions import DomainError
from pricing.models import Currency
from pricing.serializers import (
    PricingQuoteBulkRequestSerializer,
    PricingQuoteRequestSerializer,
)
from pricing.services import PricingEngine
from pricing.services.currency import resolve_property_currency
from properties.models import Property

if TYPE_CHECKING:
    from rest_framework.request import Request


def resolve_currency_param(code: str) -> Currency | None:
    """An explicit currency code → Currency (404 on unknown); blank → None,
    which lets the engine price in the rate plan's own currency (GAP-014).

    Shared with the reservations quote-options endpoint (Q-013 parity), so
    every quote-shaped endpoint resolves a currency param identically."""
    if not code:
        return None
    return get_object_or_404(Currency, code=code.upper())


def _run_quote(
    *, property: Property, currency: Currency | None, data: dict[str, Any]
) -> dict[str, Any]:
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
    permission_classes = [IsStaff]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = PricingQuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        property_obj = get_object_or_404(Property, pk=data["property_id"])
        currency = resolve_currency_param(data["currency"])
        breakdown = _run_quote(property=property_obj, currency=currency, data=data)
        return Response(breakdown)


class PricingQuoteBulkView(APIView):
    permission_classes = [IsStaff]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = PricingQuoteBulkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        currency = resolve_currency_param(data["currency"])
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
                # Q-013: no-rate entries feed the builder's manual-quote card —
                # image for parity with priced siblings, and the resolved
                # currency the operator's manual total will be saved in. Only
                # they pay the currency-resolution queries; other error codes
                # render collapsed and never show a currency.
                code = getattr(exc, "code", "domain_error")
                resolved = (
                    resolve_property_currency(property_obj) if code == "no_rate_available" else None
                )
                quotes.append(
                    {
                        "property_id": entry["property_id"],
                        "available": False,
                        "error_code": code,
                        "error_detail": str(exc),
                        "hero_image_url": property_obj.hero_image_url(),
                        "currency_code": resolved.code if resolved else None,
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
