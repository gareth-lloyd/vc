"""URL routes for the reservations API surface.

DRF's `DefaultRouter` cannot emit colon-verb URLs, so each action endpoint
gets an explicit `path()` entry alongside the router includes.
"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import SimpleRouter

from comms.views import BookingEmailViewSet
from reservations import views
from reservations.views import (
    AvailabilityBulkBlockView,
    AvailabilityDetailView,
    AvailabilityExtendHoldView,
    AvailabilityMultiView,
    AvailabilityReleaseHoldView,
    AvailabilitySearchView,
    BookingArchiveViewSet,
    BookingChargeItemViewSet,
    BookingConciergeItemViewSet,
    BookingNoteViewSet,
    BookingViewSet,
    ConciergeOverviewViewSet,
    EnquiryNoteViewSet,
    EnquiryViewSet,
    OwnerBlockViewSet,
    OwnerBookingViewSet,
    OwnerDashboardView,
    OwnerPropertyCalendarView,
    PropertyAvailabilityView,
    QuotationLineViewSet,
    QuotationViewSet,
    TermsVersionCurrentView,
    TermsVersionDetailView,
    TermsVersionListCreateView,
    TermsVersionPublishView,
)

# ----------------------------------------------------------------------
# Routers — trailing slash off to match the spec's path shape.
# ----------------------------------------------------------------------
_root = SimpleRouter(trailing_slash=False)
_root.register("guests", views.GuestViewSet, basename="guest")
_root.register("enquiries", EnquiryViewSet, basename="enquiry")
_root.register("quotations", QuotationViewSet, basename="quotation")
_root.register("bookings/archived", BookingArchiveViewSet, basename="booking-archived")
_root.register("bookings", BookingViewSet, basename="booking")


# ----------------------------------------------------------------------
# Guest action endpoints (owned by the guests subagent — kept as-is).
# ----------------------------------------------------------------------
_guest_actions: list[URLPattern | URLResolver] = [
    path(
        "guests/<int:pk>:merge",
        views.GuestMergeView.as_view({"post": "create"}),
        name="guest-merge",
    ),
    path(
        "guests/<int:pk>:anonymize",
        views.GuestAnonymizeView.as_view({"post": "create"}),
        name="guest-anonymize",
    ),
]


# ----------------------------------------------------------------------
# Colon-verb action endpoints (Enquiries)
# ----------------------------------------------------------------------
_enquiry_actions: list[URLPattern | URLResolver] = [
    path(
        "enquiries/<int:pk>:assign",
        EnquiryViewSet.as_view({"post": "assign"}),
        name="enquiry-assign",
    ),
    path(
        "enquiries/<int:pk>:convert",
        EnquiryViewSet.as_view({"post": "convert"}),
        name="enquiry-convert",
    ),
    path(
        "enquiries/<int:pk>:close",
        EnquiryViewSet.as_view({"post": "close"}),
        name="enquiry-close",
    ),
    path(
        "enquiries/<int:pk>:reopen",
        EnquiryViewSet.as_view({"post": "reopen"}),
        name="enquiry-reopen",
    ),
    path(
        "enquiries/<int:pk>/activity",
        EnquiryViewSet.as_view({"get": "activity"}),
        name="enquiry-activity",
    ),
    path(
        "enquiries/<int:enquiry_pk>/notes",
        EnquiryNoteViewSet.as_view({"get": "list", "post": "create"}),
        name="enquiry-notes",
    ),
]


# ----------------------------------------------------------------------
# Colon-verb action endpoints (Quotations)
# ----------------------------------------------------------------------
_quotation_actions: list[URLPattern | URLResolver] = [
    path(
        "quotations/<int:pk>:preview",
        QuotationViewSet.as_view({"get": "preview"}),
        name="quotation-preview",
    ),
    path(
        "quotations/<int:pk>:send",
        QuotationViewSet.as_view({"post": "send_quote"}),
        name="quotation-send",
    ),
    path(
        "quotations/<int:pk>:mark-manually-sent",
        QuotationViewSet.as_view({"post": "mark_manually_sent"}),
        name="quotation-mark-manually-sent",
    ),
    path(
        "quotations/<int:pk>:duplicate",
        QuotationViewSet.as_view({"post": "duplicate"}),
        name="quotation-duplicate",
    ),
    path(
        "quotations/<int:pk>:convert",
        QuotationViewSet.as_view({"post": "convert"}),
        name="quotation-convert",
    ),
    path(
        "quotations/<int:pk>:withdraw",
        QuotationViewSet.as_view({"post": "withdraw"}),
        name="quotation-withdraw",
    ),
    path(
        "quotations/<int:quotation_pk>/lines",
        QuotationLineViewSet.as_view({"get": "list", "post": "create"}),
        name="quotation-lines",
    ),
    path(
        "quotations/<int:quotation_pk>/lines/<int:pk>",
        QuotationLineViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="quotation-line-detail",
    ),
    path(
        "quotations/<int:quotation_pk>/lines:reorder",
        QuotationLineViewSet.as_view({"post": "reorder"}),
        name="quotation-lines-reorder",
    ),
]


# ----------------------------------------------------------------------
# Colon-verb action endpoints (Bookings)
# ----------------------------------------------------------------------
_booking_actions: list[URLPattern | URLResolver] = [
    path(
        "bookings/<int:pk>:confirm",
        BookingViewSet.as_view({"post": "confirm"}),
        name="booking-confirm",
    ),
    path(
        "bookings/<int:pk>:cancel",
        BookingViewSet.as_view({"post": "cancel"}),
        name="booking-cancel",
    ),
    path(
        "bookings/<int:pk>:owner-approve",
        BookingViewSet.as_view({"post": "owner_approve"}),
        name="booking-owner-approve",
    ),
    path(
        "bookings/<int:pk>:owner-decline",
        BookingViewSet.as_view({"post": "owner_decline"}),
        name="booking-owner-decline",
    ),
    path(
        "bookings/<int:pk>:modify-dates",
        BookingViewSet.as_view({"post": "modify_dates"}),
        name="booking-modify-dates",
    ),
    path(
        "bookings/<int:pk>:modify-guests",
        BookingViewSet.as_view({"post": "modify_guests"}),
        name="booking-modify-guests",
    ),
    path(
        "bookings/<int:pk>:archive",
        BookingViewSet.as_view({"post": "archive"}),
        name="booking-archive",
    ),
    path(
        "bookings/<int:pk>:restore",
        BookingViewSet.as_view({"post": "restore"}),
        name="booking-restore",
    ),
    path(
        "bookings/<int:pk>:check-in",
        BookingViewSet.as_view({"post": "check_in"}),
        name="booking-check-in",
    ),
    path(
        "bookings/<int:pk>:check-out",
        BookingViewSet.as_view({"post": "check_out"}),
        name="booking-check-out",
    ),
    path(
        "bookings/<int:pk>:resend-confirmation",
        BookingViewSet.as_view({"post": "resend_confirmation"}),
        name="booking-resend-confirmation",
    ),
    path(
        "bookings/<int:pk>/activity",
        BookingViewSet.as_view({"get": "activity"}),
        name="booking-activity",
    ),
    # Emails nested (delegated to comms.BookingEmailViewSet — booking has no
    # FK to EmailLog; the viewset filters by `correlation__booking_id`).
    path(
        "bookings/<int:booking_pk>/emails",
        BookingEmailViewSet.as_view({"get": "list"}),
        name="booking-emails",
    ),
    path(
        "bookings/<int:booking_pk>/emails/<int:pk>:resend",
        BookingEmailViewSet.as_view({"post": "resend"}),
        name="booking-email-resend",
    ),
    # Notes nested
    path(
        "bookings/<int:booking_pk>/notes",
        BookingNoteViewSet.as_view({"get": "list", "post": "create"}),
        name="booking-notes",
    ),
    path(
        "bookings/<int:booking_pk>/notes/<int:pk>",
        BookingNoteViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="booking-note-detail",
    ),
]


# ----------------------------------------------------------------------
# Charge-item nested routes
# ----------------------------------------------------------------------
_charge_routes: list[URLPattern | URLResolver] = [
    path(
        "bookings/<int:booking_pk>/charge-items",
        BookingChargeItemViewSet.as_view({"get": "list", "post": "create"}),
        name="booking-charge-items",
    ),
    path(
        "bookings/<int:booking_pk>/charge-items/<int:pk>",
        BookingChargeItemViewSet.as_view(
            {
                "get": "retrieve",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="booking-charge-item-detail",
    ),
]


# ----------------------------------------------------------------------
# Concierge nested routes
# ----------------------------------------------------------------------
_concierge_routes: list[URLPattern | URLResolver] = [
    path(
        "bookings/<int:booking_pk>/concierge-items",
        BookingConciergeItemViewSet.as_view({"get": "list", "post": "create"}),
        name="booking-concierge-items",
    ),
    path(
        "bookings/<int:booking_pk>/concierge-items/<int:pk>",
        BookingConciergeItemViewSet.as_view(
            {
                "get": "retrieve",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="booking-concierge-item-detail",
    ),
    path(
        "bookings/<int:booking_pk>/concierge-items:reorder",
        BookingConciergeItemViewSet.as_view({"post": "reorder"}),
        name="booking-concierge-items-reorder",
    ),
    path(
        "bookings/<int:booking_pk>/concierge-items/<int:pk>:confirm",
        BookingConciergeItemViewSet.as_view({"post": "confirm"}),
        name="booking-concierge-item-confirm",
    ),
]


# ----------------------------------------------------------------------
# Concierge coverage matrix (cross-booking overview + per-cell set-status)
# ----------------------------------------------------------------------
_concierge_overview_routes: list[URLPattern | URLResolver] = [
    path(
        "concierge/overview",
        ConciergeOverviewViewSet.as_view({"get": "list"}),
        name="concierge-overview",
    ),
    path(
        "concierge/<int:booking_id>/coverage/<str:service>:set-status",
        ConciergeOverviewViewSet.as_view({"post": "set_status"}),
        name="concierge-coverage-set-status",
    ),
]


_availability_routes: list[URLPattern | URLResolver] = [
    path(
        "properties/<int:property_id>/availability",
        PropertyAvailabilityView.as_view(),
        name="property-availability",
    ),
    path(
        "availability",
        AvailabilityMultiView.as_view(),
        name="availability-multi",
    ),
    path(
        "availability:search",
        AvailabilitySearchView.as_view(),
        name="availability-search",
    ),
    path(
        "availability:bulk-block",
        AvailabilityBulkBlockView.as_view(),
        name="availability-bulk-block",
    ),
    path(
        "availability/<int:pk>",
        AvailabilityDetailView.as_view(),
        name="availability-detail",
    ),
    path(
        "availability/<int:pk>:extend-hold",
        AvailabilityExtendHoldView.as_view(),
        name="availability-extend-hold",
    ),
    path(
        "availability/<int:pk>:release-hold",
        AvailabilityReleaseHoldView.as_view(),
        name="availability-release-hold",
    ),
]


_terms_routes: list[URLPattern | URLResolver] = [
    path(
        "terms-versions",
        TermsVersionListCreateView.as_view(),
        name="terms-version-list",
    ),
    path(
        "terms-versions/current",
        TermsVersionCurrentView.as_view(),
        name="terms-version-current",
    ),
    path(
        "terms-versions/<str:version>",
        TermsVersionDetailView.as_view(),
        name="terms-version-detail",
    ),
    path(
        "terms-versions/<str:version>:publish",
        TermsVersionPublishView.as_view(),
        name="terms-version-publish",
    ),
]


_owner_routes: list[URLPattern | URLResolver] = [
    path("owner/dashboard", OwnerDashboardView.as_view(), name="owner-dashboard"),
    path(
        "owner/bookings",
        OwnerBookingViewSet.as_view({"get": "list"}),
        name="owner-booking-list",
    ),
    path(
        "owner/bookings/<int:pk>",
        OwnerBookingViewSet.as_view({"get": "retrieve"}),
        name="owner-booking-detail",
    ),
    path(
        "owner/bookings/<int:pk>:approve",
        OwnerBookingViewSet.as_view({"post": "approve"}),
        name="owner-booking-approve",
    ),
    path(
        "owner/bookings/<int:pk>:decline",
        OwnerBookingViewSet.as_view({"post": "decline"}),
        name="owner-booking-decline",
    ),
    path(
        "owner/properties/<int:property_id>/calendar",
        OwnerPropertyCalendarView.as_view(),
        name="owner-property-calendar",
    ),
    path(
        "owner/block-requests",
        OwnerBlockViewSet.as_view({"get": "list", "post": "create"}),
        name="owner-block-request-list",
    ),
    path(
        "owner/block-requests/<int:pk>:cancel",
        OwnerBlockViewSet.as_view({"post": "cancel"}),
        name="owner-block-request-cancel",
    ),
]


# Staff-facing owner-block awareness feed.
_owner_block_update_routes: list[URLPattern | URLResolver] = [
    path(
        "owner-block-updates",
        views.OwnerBlockUpdateViewSet.as_view({"get": "list"}),
        name="owner-block-update-list",
    ),
    path(
        "owner-block-updates/<int:pk>:seen",
        views.OwnerBlockUpdateViewSet.as_view({"post": "seen"}),
        name="owner-block-update-seen",
    ),
    path(
        "owner-block-updates/<int:pk>:unseen",
        views.OwnerBlockUpdateViewSet.as_view({"post": "unseen"}),
        name="owner-block-update-unseen",
    ),
    path(
        "owner-block-updates/<int:pk>:contest",
        views.OwnerBlockUpdateViewSet.as_view({"post": "contest"}),
        name="owner-block-update-contest",
    ),
]


urlpatterns: list[URLPattern | URLResolver] = [
    # Action / nested patterns precede the router's CRUD routes: DRF's
    # `/<pk>` regex (`[^/.]+`) would otherwise swallow `1:merge` as the pk.
    *_guest_actions,
    *_owner_routes,
    *_owner_block_update_routes,
    *_enquiry_actions,
    *_quotation_actions,
    *_booking_actions,
    *_charge_routes,
    *_concierge_routes,
    *_concierge_overview_routes,
    *_availability_routes,
    *_terms_routes,
    path("", include(_root.urls)),
]
