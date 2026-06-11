"""`POST /quotations:search-options` — the quote builder's search endpoint.

Supersedes the builder's use of `/pricing:quote-bulk`: same flattened
breakdown / Q-013 error rows, plus per-property `stay_options` (changeover
blocks inside the `preferred ± flex_days` window). Lives in reservations
because the availability flags need the booking/hold models, which pricing
may not import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import IsStaff
from pricing.views.quote import resolve_currency_param
from reservations.serializers.quote_options import QuoteSearchOptionsRequestSerializer
from reservations.services.stay_options import StayOptionsService

if TYPE_CHECKING:
    from rest_framework.request import Request


class QuotationSearchOptionsView(APIView):
    permission_classes = [IsStaff]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = QuoteSearchOptionsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        quotes = StayOptionsService.search(
            requests=data["requests"],
            flex_days=data["flex_days"],
            currency=resolve_currency_param(data["currency"]),
        )
        return Response({"quotes": quotes})
