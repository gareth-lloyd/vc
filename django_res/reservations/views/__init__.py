"""DRF views for the reservations app."""

from __future__ import annotations

from reservations.views.availability import (
    AvailabilityBulkBlockView,
    AvailabilityDetailView,
    AvailabilityExtendHoldView,
    AvailabilityMultiView,
    AvailabilityReleaseHoldView,
    AvailabilitySearchView,
    PropertyAvailabilityView,
)
from reservations.views.block_request import BlockRequestViewSet
from reservations.views.booking import (
    BookingArchiveViewSet,
    BookingNoteViewSet,
    BookingViewSet,
)
from reservations.views.concierge import BookingConciergeItemViewSet
from reservations.views.concierge_overview import ConciergeOverviewViewSet
from reservations.views.enquiry import EnquiryNoteViewSet, EnquiryViewSet
from reservations.views.guest import (
    GuestAnonymizeView,
    GuestMergeView,
    GuestViewSet,
)
from reservations.views.owner import (
    OwnerBlockViewSet,
    OwnerBookingViewSet,
    OwnerDashboardView,
    OwnerPropertyCalendarView,
)
from reservations.views.quotation import QuotationLineViewSet, QuotationViewSet
from reservations.views.terms import (
    TermsVersionCurrentView,
    TermsVersionDetailView,
    TermsVersionListCreateView,
    TermsVersionPublishView,
)

__all__ = [
    "AvailabilityBulkBlockView",
    "AvailabilityDetailView",
    "AvailabilityExtendHoldView",
    "AvailabilityMultiView",
    "AvailabilityReleaseHoldView",
    "AvailabilitySearchView",
    "BlockRequestViewSet",
    "BookingArchiveViewSet",
    "BookingConciergeItemViewSet",
    "BookingNoteViewSet",
    "BookingViewSet",
    "ConciergeOverviewViewSet",
    "EnquiryNoteViewSet",
    "EnquiryViewSet",
    "GuestAnonymizeView",
    "GuestMergeView",
    "GuestViewSet",
    "OwnerBlockViewSet",
    "OwnerBookingViewSet",
    "OwnerDashboardView",
    "OwnerPropertyCalendarView",
    "PropertyAvailabilityView",
    "QuotationLineViewSet",
    "QuotationViewSet",
    "TermsVersionCurrentView",
    "TermsVersionDetailView",
    "TermsVersionListCreateView",
    "TermsVersionPublishView",
]
