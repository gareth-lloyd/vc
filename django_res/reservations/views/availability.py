"""Views for the availability surface.

`Availability` records are stored as `BookingHold` rows. The API exposes a
calendar slice (GET) and write/update/delete on individual blocks plus
search/bulk operations.

Calendar reads come from `reservations.services.AvailabilityService` (computes
per-day cell status) — keep all business logic out of the view.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import IsReservationsWriter, IsStaff
from core.exceptions import DomainError, ReadOnlyHold
from properties.models import Property
from reservations.enums import OPERATOR_EDITABLE_HOLD_REASONS
from reservations.serializers.availability import (
    AvailabilityBulkBlockSerializer,
    AvailabilityExtendHoldSerializer,
    AvailabilityRecordSerializer,
    AvailabilitySearchSerializer,
    AvailabilityWriteSerializer,
)
from reservations.services import AvailabilityService
from reservations.services.holds import HoldService

if TYPE_CHECKING:
    from rest_framework.request import Request


_EDITABLE_REASONS = frozenset(OPERATOR_EDITABLE_HOLD_REASONS)


def _serialize_segment(cell: Any) -> dict[str, Any]:
    return {
        "available": cell.available,
        "reason": cell.reason,
        "block_id": cell.block_id,
        "quotation_id": cell.quotation_id,
    }


def _serialize_cell(day: date, cell: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "date": day.isoformat(),
        "available": cell.available,
        "reason": cell.reason,
        "block_id": cell.block_id,
        "quotation_id": cell.quotation_id,
    }
    if cell.segments is not None:
        payload["segments"] = {
            "am": _serialize_segment(cell.segments["am"]),
            "pm": _serialize_segment(cell.segments["pm"]),
        }
    return payload


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _default_expiry(reason: str) -> datetime:
    """Reasonable default expiry for owner/maintenance/manual blocks.

    These blocks are open-ended by nature; we expire them far in the future so
    a hold is "live" until released or hard-edited.
    """
    return timezone.now() + timedelta(days=365 * 10)


class PropertyAvailabilityView(APIView):
    """`GET / POST /properties/{id}/availability`."""

    def get_permissions(self) -> list[Any]:
        if self.request.method == "GET":
            return [IsStaff()]
        return [IsReservationsWriter()]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        range_start = _parse_date(request.query_params.get("from"))
        range_end = _parse_date(request.query_params.get("to"))
        if not range_start or not range_end:
            return Response(
                {
                    "code": "validation_error",
                    "detail": "`from` and `to` query params are required (YYYY-MM-DD)",
                    "field_errors": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        cells = AvailabilityService.calendar(property_obj, range_start, range_end)
        data = [_serialize_cell(day, cell) for day, cell in sorted(cells.items())]
        return Response({"property_id": property_obj.pk, "cells": data})

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        serializer = AvailabilityWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        expires_at = data.get("expires_at") or _default_expiry(data["reason"])
        hold = HoldService.place(
            property=property_obj,
            date_from=data["date_from"],
            date_to=data["date_to"],
            expires_at=expires_at,
            reason=data["reason"],
            notes=data.get("notes", ""),
        )
        return Response(
            AvailabilityRecordSerializer(hold).data,
            status=status.HTTP_201_CREATED,
        )


class AvailabilityDetailView(generics.GenericAPIView):
    """`PATCH / DELETE /availability/{id}`.

    `DELETE` releases the hold (`released_at = now`); `PATCH` updates expiry /
    dates without releasing.
    """

    serializer_class = AvailabilityRecordSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> Any:
        from reservations.models.booking import BookingHold

        return BookingHold.objects.all()

    def _editable_or_raise(self, hold: Any) -> None:
        """System holds (quotation / booking) are read-only here."""
        if (
            hold.reason not in _EDITABLE_REASONS
            or hold.quotation_id is not None
            or hold.booking_id is not None
        ):
            raise ReadOnlyHold(
                "This hold is managed by its quotation or booking and cannot "
                "be edited from the availability calendar."
            )

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        hold = self.get_object()
        self._editable_or_raise(hold)
        body = request.data if isinstance(request.data, dict) else {}
        date_from = _parse_date(body.get("date_from")) or hold.date_from
        date_to = _parse_date(body.get("date_to")) or hold.date_to
        if date_to <= date_from:
            raise serializers.ValidationError({"date_to": "`date_to` must be after `date_from`."})
        reason = body.get("reason", hold.reason)
        if reason not in _EDITABLE_REASONS:
            raise ReadOnlyHold(f"`{reason}` is not an operator-editable block reason.")
        notes = body.get("notes", hold.notes)
        hold = HoldService.update_block(
            hold,
            date_from=date_from,
            date_to=date_to,
            reason=reason,
            notes=notes,
        )
        return Response(AvailabilityRecordSerializer(hold).data)

    def delete(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        hold = self.get_object()
        self._editable_or_raise(hold)
        HoldService.release(hold)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AvailabilityMultiView(APIView):
    """`GET /availability` — multi-villa lookup."""

    permission_classes = [IsStaff]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from reservations.models.booking import BookingHold

        ids_param = request.query_params.get("property_ids", "")
        property_ids = [int(part) for part in ids_param.split(",") if part.strip().isdigit()]
        range_start = _parse_date(request.query_params.get("from"))
        range_end = _parse_date(request.query_params.get("to"))
        if not property_ids or not range_start or not range_end:
            return Response(
                {
                    "code": "validation_error",
                    "detail": "`property_ids`, `from`, `to` are required",
                    "field_errors": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        holds = BookingHold.objects.filter(
            property_id__in=property_ids,
            released_at__isnull=True,
            date_to__gt=range_start,
            date_from__lt=range_end,
        )
        return Response({"records": AvailabilityRecordSerializer(holds, many=True).data})


class AvailabilitySearchView(APIView):
    """`POST /availability:search` — find villas free in a window."""

    permission_classes = [IsStaff]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from reservations.models.booking import BookingHold

        serializer = AvailabilitySearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        qs = Property.objects.all()
        filters = data.get("filters") or {}
        if region := filters.get("region"):
            qs = qs.filter(region__slug=region)
        if country := filters.get("country"):
            qs = qs.filter(region__country__iso2__iexact=country)
        if min_bedrooms := filters.get("min_bedrooms"):
            qs = qs.filter(capacity__bedrooms__gte=int(min_bedrooms))
        # Subtract villas with a blocking hold overlapping the window.
        blocked = set(
            BookingHold.objects.filter(
                property__in=qs,
                released_at__isnull=True,
                date_to__gt=data["date_from"],
                date_from__lt=data["date_to"],
            ).values_list("property_id", flat=True)
        )
        result = [
            {
                "property_id": p.pk,
                "available": p.pk not in blocked,
                "name": p.display_name or p.name,
                "slug": p.slug,
            }
            for p in qs
        ]
        return Response({"results": result})


class AvailabilityBulkBlockView(APIView):
    """`POST /availability:bulk-block`."""

    permission_classes = [IsReservationsWriter]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = AvailabilityBulkBlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        expires_at = data.get("expires_at") or _default_expiry(data["reason"])
        property_ids = list(data["property_ids"])
        properties = Property.objects.in_bulk(property_ids)
        records: list[Any] = []
        failures: list[dict[str, Any]] = []
        for property_id in property_ids:
            property_obj = properties.get(property_id)
            if property_obj is None:
                failures.append({"property_id": property_id, "error": "not_found"})
                continue
            try:
                records.append(
                    HoldService.place(
                        property=property_obj,
                        date_from=data["date_from"],
                        date_to=data["date_to"],
                        expires_at=expires_at,
                        reason=data["reason"],
                    )
                )
            except DomainError as exc:
                failures.append({"property_id": property_id, "code": exc.code, "detail": str(exc)})
        return Response(
            {
                "records": AvailabilityRecordSerializer(records, many=True).data,
                "failures": failures,
            },
            status=status.HTTP_201_CREATED,
        )


class AvailabilityExtendHoldView(APIView):
    """`POST /availability/{id}:extend-hold`."""

    permission_classes = [IsReservationsWriter]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from reservations.models.booking import BookingHold

        hold = get_object_or_404(BookingHold, pk=self.kwargs["pk"])
        if hold.expires_at is None:
            # An indefinite block (owner/maintenance) has no expiry to extend.
            # Writing a finite `expires_at` would let `expire_holds` reap it;
            # release-hold is the way to remove it.
            raise ReadOnlyHold(
                "This block never expires and cannot be given an expiry; release it instead."
            )
        serializer = AvailabilityExtendHoldSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hold.expires_at = serializer.validated_data["expires_at"]
        hold.save(update_fields=["expires_at", "updated_at"])
        return Response(AvailabilityRecordSerializer(hold).data)


class AvailabilityReleaseHoldView(APIView):
    """`POST /availability/{id}:release-hold`."""

    permission_classes = [IsReservationsWriter]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from reservations.models.booking import BookingHold

        hold = get_object_or_404(BookingHold, pk=self.kwargs["pk"])
        HoldService.release(hold)
        return Response(AvailabilityRecordSerializer(hold).data)
