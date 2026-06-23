"""DRF serializers for the reservations app."""

from __future__ import annotations

from reservations.serializers.booking import (
    BookingDetailSerializer,
    BookingListSerializer,
    BookingNoteSerializer,
    BookingWriteSerializer,
)
from reservations.serializers.charge_item import (
    BookingChargeItemSerializer,
    BookingChargeItemWriteSerializer,
)
from reservations.serializers.client import ClientListSerializer
from reservations.serializers.concierge import (
    BookingConciergeItemSerializer,
    BookingConciergeItemWriteSerializer,
)
from reservations.serializers.contact import (
    ContactBookingSerializer,
    ContactEnquirySerializer,
    ContactQuotationSerializer,
    ContactTravelPreferenceSerializer,
)
from reservations.serializers.enquiry import (
    EnquiryDetailSerializer,
    EnquiryEventSerializer,
    EnquiryListSerializer,
    EnquiryNoteSerializer,
    EnquiryWriteSerializer,
)
from reservations.serializers.quotation import (
    QuotationDetailSerializer,
    QuotationLineSerializer,
    QuotationLineWriteSerializer,
    QuotationListSerializer,
    QuotationWriteSerializer,
)

__all__ = [
    "BookingChargeItemSerializer",
    "BookingChargeItemWriteSerializer",
    "BookingConciergeItemSerializer",
    "BookingConciergeItemWriteSerializer",
    "BookingDetailSerializer",
    "BookingListSerializer",
    "BookingNoteSerializer",
    "BookingWriteSerializer",
    "ClientListSerializer",
    "ContactBookingSerializer",
    "ContactEnquirySerializer",
    "ContactQuotationSerializer",
    "ContactTravelPreferenceSerializer",
    "EnquiryDetailSerializer",
    "EnquiryEventSerializer",
    "EnquiryListSerializer",
    "EnquiryNoteSerializer",
    "EnquiryWriteSerializer",
    "QuotationDetailSerializer",
    "QuotationLineSerializer",
    "QuotationLineWriteSerializer",
    "QuotationListSerializer",
    "QuotationWriteSerializer",
]
