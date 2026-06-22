"""Person-scoped customer history reads.

`GAP-045` Unit 3d-1: `/contacts/{id}/bookings|enquiries|quotations|
travel-preferences` replace the old `/guests/{id}/...` history reads (deleted in
D4) but key on the unified `accounts.Person`. Hosted from `reservations/urls.py`
— `accounts` is
the bottom of the import spine and cannot serialise reservations rows, so the
routes live here (a clean downward reservations → accounts edge; precedent:
`reservations/urls.py` already hosts `comms.views.BookingEmailViewSet`).

These reads resolve a Person by pk directly. With Guest folded into Person
(GAP-045 D5), this is the surviving customer-history surface.
"""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Prefetch, QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from accounts.models import Person
from core.api import IsStaff
from reservations.models import Booking, Quotation, QuotationLine
from reservations.serializers import (
    ContactBookingSerializer,
    ContactEnquirySerializer,
    ContactQuotationSerializer,
    ContactTravelPreferenceSerializer,
)


def _enquiry_history_prefetch() -> Prefetch:
    """The 3-level quote-stack the history serializer walks (quotations →
    selected lines → live bookings), applied to a customer's enquiry queryset so
    the enquiry-history read stays query-bounded regardless of row count.

    `booking-`-prefixed synthetic quotations (BookingLoader legacy-fill rows)
    are excluded at the source, so the prefetch cache `ContactEnquirySerializer`
    reads is already clean — they must not inflate `quote_count` or
    mis-attribute the converted booking.
    """
    bookings = Booking.objects.only(
        "id", "reference", "status", "is_archived", "created_at", "quotation_line_id"
    )
    lines = QuotationLine.objects.prefetch_related(Prefetch("bookings", queryset=bookings))
    quotations = Quotation.objects.real().prefetch_related(Prefetch("lines", queryset=lines))
    return Prefetch("quotations", queryset=quotations)


class ContactCustomerReadViewSet(viewsets.GenericViewSet[Person]):
    """Nested customer-history reads keyed on a Person (`contact_pk`)."""

    queryset = Person.objects.all()
    permission_classes = [IsStaff]

    def _person(self, contact_pk: str | None) -> Person:
        return get_object_or_404(Person, pk=contact_pk)

    def _paginated(
        self, qs: QuerySet[Any], serializer_class: type[BaseSerializer[Any]]
    ) -> Response:
        page = self.paginate_queryset(cast(Any, qs))
        ser = serializer_class(page if page is not None else qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

    def bookings(self, request: Request, contact_pk: str | None = None) -> Response:
        person = self._person(contact_pk)
        qs = person.bookings_as_customer.all().order_by("-created_at")
        return self._paginated(qs, ContactBookingSerializer)

    def enquiries(self, request: Request, contact_pk: str | None = None) -> Response:
        person = self._person(contact_pk)
        qs = (
            person.enquiries_as_customer.all()
            .order_by("-created_at")
            .prefetch_related(_enquiry_history_prefetch())
        )
        return self._paginated(qs, ContactEnquirySerializer)

    def quotations(self, request: Request, contact_pk: str | None = None) -> Response:
        person = self._person(contact_pk)
        # `.real()` drops the BookingLoader's `booking-` synthetic fill rows —
        # the shared exclusion every Quotation-surfacing read routes through.
        qs = person.quotations_as_customer.real().order_by("-created_at")
        return self._paginated(qs, ContactQuotationSerializer)

    def travel_preferences(self, request: Request, contact_pk: str | None = None) -> Response:
        person = self._person(contact_pk)
        qs = person.travel_preferences.select_related("preference_type").order_by(
            "preference_type__name"
        )
        return self._paginated(qs, ContactTravelPreferenceSerializer)
