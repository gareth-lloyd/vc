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
    WeeklyPricesView,
)
from reservations.views.booking import (
    BookingArchiveViewSet,
    BookingNoteViewSet,
    BookingViewSet,
)
from reservations.views.charge_item import BookingChargeItemViewSet
from reservations.views.client import ClientListView
from reservations.views.concierge import BookingConciergeItemViewSet
from reservations.views.concierge_overview import ConciergeOverviewViewSet
from reservations.views.contact_reads import ContactCustomerReadViewSet
from reservations.views.damage_claim import (
    DamageClaimPhotoDetailView,
    DamageClaimPhotoListCreateView,
    DamageClaimViewSet,
)
from reservations.views.enquiry import EnquiryNoteViewSet, EnquiryViewSet
from reservations.views.owner import (
    OwnerBlockViewSet,
    OwnerBookingViewSet,
    OwnerDashboardView,
    OwnerPropertyCalendarView,
)
from reservations.views.owner_block_update import OwnerBlockUpdateViewSet
from reservations.views.quotation import QuotationLineViewSet, QuotationViewSet
from reservations.views.quote_options import QuotationSearchOptionsView
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
    "BookingArchiveViewSet",
    "BookingChargeItemViewSet",
    "BookingConciergeItemViewSet",
    "BookingNoteViewSet",
    "BookingViewSet",
    "ClientListView",
    "ConciergeOverviewViewSet",
    "ContactCustomerReadViewSet",
    "DamageClaimPhotoDetailView",
    "DamageClaimPhotoListCreateView",
    "DamageClaimViewSet",
    "EnquiryNoteViewSet",
    "EnquiryViewSet",
    "OwnerBlockUpdateViewSet",
    "OwnerBlockViewSet",
    "OwnerBookingViewSet",
    "OwnerDashboardView",
    "OwnerPropertyCalendarView",
    "PropertyAvailabilityView",
    "QuotationLineViewSet",
    "QuotationSearchOptionsView",
    "QuotationViewSet",
    "TermsVersionCurrentView",
    "TermsVersionDetailView",
    "TermsVersionListCreateView",
    "TermsVersionPublishView",
    "WeeklyPricesView",
]
