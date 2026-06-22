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
    OwnerBlock,
    Quotation,
    QuotationLine,
    TermsVersion,
)


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("reference", "status", "property", "date_from", "date_to", "created_at")
    list_filter = ("status", "site_source")
    search_fields = ("reference", "email", "first_name", "last_name")
    raw_id_fields = ("person", "agent")


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
    raw_id_fields = ("person", "agent")


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
    raw_id_fields = ("person", "agent")


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
    list_display = ("pk", "booking", "person", "role", "email_override")
    list_filter = ("role",)
    search_fields = (
        "booking__reference",
        "person__last_name",
        "person__first_name",
        "person__emails__email",
    )
    raw_id_fields = ("booking", "person")


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
