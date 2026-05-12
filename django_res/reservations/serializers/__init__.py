"""DRF serializers for the reservations app."""

from __future__ import annotations

from reservations.serializers.booking import (
    BookingDetailSerializer,
    BookingListSerializer,
    BookingNoteSerializer,
    BookingWriteSerializer,
)
from reservations.serializers.concierge import (
    BookingConciergeItemSerializer,
    BookingConciergeItemWriteSerializer,
)
from reservations.serializers.enquiry import (
    EnquiryDetailSerializer,
    EnquiryEventSerializer,
    EnquiryListSerializer,
    EnquiryNoteSerializer,
    EnquiryWriteSerializer,
)
from reservations.serializers.guest import (
    GuestBookingSerializer,
    GuestEnquirySerializer,
    GuestMergeSerializer,
    GuestQuotationSerializer,
    GuestSerializer,
)
from reservations.serializers.quotation import (
    QuotationDetailSerializer,
    QuotationLineSerializer,
    QuotationLineWriteSerializer,
    QuotationListSerializer,
    QuotationWriteSerializer,
)

__all__ = [
    "BookingConciergeItemSerializer",
    "BookingConciergeItemWriteSerializer",
    "BookingDetailSerializer",
    "BookingListSerializer",
    "BookingNoteSerializer",
    "BookingWriteSerializer",
    "EnquiryDetailSerializer",
    "EnquiryEventSerializer",
    "EnquiryListSerializer",
    "EnquiryNoteSerializer",
    "EnquiryWriteSerializer",
    "GuestBookingSerializer",
    "GuestEnquirySerializer",
    "GuestMergeSerializer",
    "GuestQuotationSerializer",
    "GuestSerializer",
    "QuotationDetailSerializer",
    "QuotationLineSerializer",
    "QuotationLineWriteSerializer",
    "QuotationListSerializer",
    "QuotationWriteSerializer",
]
