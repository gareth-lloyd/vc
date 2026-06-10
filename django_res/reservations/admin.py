"""Basic admin registrations for the reservations app."""

from __future__ import annotations

from django.contrib import admin

from reservations.models import (
    Booking,
    BookingConciergeItem,
    BookingEvent,
    BookingGuest,
    BookingHold,
    BookingNote,
    Enquiry,
    EnquiryEvent,
    EnquiryNote,
    Guest,
    OwnerBlock,
    Quotation,
    QuotationLine,
    TermsVersion,
)


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ("pk", "last_name", "first_name", "email", "status")
    list_filter = ("status",)
    search_fields = ("first_name", "last_name", "email")


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("reference", "status", "property", "date_from", "date_to", "created_at")
    list_filter = ("status", "site_source")
    search_fields = ("reference", "email", "first_name", "last_name")


@admin.register(EnquiryNote)
class EnquiryNoteAdmin(admin.ModelAdmin):
    list_display = ("pk", "enquiry", "kind", "is_pinned", "created_at")
    list_filter = ("kind",)


@admin.register(EnquiryEvent)
class EnquiryEventAdmin(admin.ModelAdmin):
    list_display = ("pk", "enquiry", "from_status", "to_status", "kind", "created_at")
    list_filter = ("kind",)


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ("reference", "status", "expires_at")
    list_filter = ("status",)
    search_fields = ("reference",)


@admin.register(QuotationLine)
class QuotationLineAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "quotation",
        "property",
        "currency",
        "date_from",
        "date_to",
        "total",
        "is_selected",
    )
    list_filter = ("is_selected",)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "status",
        "property",
        "date_from",
        "date_to",
        "balance_due",
        "is_archived",
    )
    list_filter = ("status", "is_archived", "payment_method")
    search_fields = ("reference",)


@admin.register(BookingHold)
class BookingHoldAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "property",
        "date_from",
        "date_to",
        "expires_at",
        "released_at",
        "reason",
    )
    list_filter = ("reason",)


@admin.register(BookingEvent)
class BookingEventAdmin(admin.ModelAdmin):
    list_display = ("pk", "booking", "from_status", "to_status", "source", "created_at")
    list_filter = ("source",)


@admin.register(BookingNote)
class BookingNoteAdmin(admin.ModelAdmin):
    list_display = ("pk", "booking", "kind", "visibility", "is_pinned", "created_at")
    list_filter = ("kind", "visibility")


@admin.register(BookingGuest)
class BookingGuestAdmin(admin.ModelAdmin):
    list_display = ("pk", "booking", "guest", "role", "email_override")
    list_filter = ("role",)
    search_fields = ("booking__reference", "guest__email", "guest__last_name")
    raw_id_fields = ("booking", "guest")


@admin.register(BookingConciergeItem)
class BookingConciergeItemAdmin(admin.ModelAdmin):
    list_display = ("pk", "booking", "tier", "name", "quantity", "unit_price", "status")
    list_filter = ("tier", "status")


@admin.register(TermsVersion)
class TermsVersionAdmin(admin.ModelAdmin):
    list_display = ("version", "is_current", "published_at", "created_at")
    list_filter = ("is_current",)


@admin.register(OwnerBlock)
class OwnerBlockAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "property",
        "created_by",
        "date_from",
        "date_to",
        "kind",
        "status",
    )
    list_filter = ("status", "kind")
    search_fields = ("property__name", "created_by__email")
