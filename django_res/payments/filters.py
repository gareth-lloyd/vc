"""FilterSets for payments collection endpoints."""

from __future__ import annotations

from django_filters import rest_framework as filters

from payments.models import Payment, Refund


class PaymentFilter(filters.FilterSet):
    """Filter shape for `GET /payments`."""

    purpose = filters.CharFilter(field_name="purpose")
    gateway = filters.CharFilter(field_name="provider")
    status = filters.CharFilter(field_name="status")
    currency = filters.CharFilter(field_name="currency__code")
    booking = filters.NumberFilter(field_name="booking_id")
    created_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    settled_after = filters.IsoDateTimeFilter(field_name="settled_at", lookup_expr="gte")
    settled_before = filters.IsoDateTimeFilter(field_name="settled_at", lookup_expr="lte")

    class Meta:
        model = Payment
        fields = [
            "purpose",
            "gateway",
            "status",
            "currency",
            "booking",
            "created_after",
            "created_before",
            "settled_after",
            "settled_before",
        ]


class RefundFilter(filters.FilterSet):
    """Filter shape for `GET /refunds`."""

    booking = filters.NumberFilter(field_name="booking_id")
    status = filters.CharFilter(field_name="status")
    created_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Refund
        fields = ["booking", "status", "created_after", "created_before"]
