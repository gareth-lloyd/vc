"""TextChoices used across the reservations app.

Kept flat in one module to make the closed sets easy to scan and reuse.
"""

from __future__ import annotations

from django.db import models


class GuestStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"
    ANONYMIZED = "anonymized", "Anonymized"


class ContactMethod(models.TextChoices):
    EMAIL = "email", "Email"
    PHONE = "phone", "Phone"
    SMS = "sms", "SMS"


class EnquiryStatus(models.TextChoices):
    NEW = "new", "New"
    CONTACTED = "contacted", "Contacted"
    QUOTED = "quoted", "Quoted"
    LOST = "lost", "Lost"
    CONVERTED = "converted", "Converted"


class EnquirySource(models.TextChoices):
    MAIN_WEBSITE = "main_website", "Main website"
    AGENT_PORTAL = "agent_portal", "Agent portal"
    EMAIL_INBOUND = "email_inbound", "Inbound email"
    PHONE = "phone", "Phone"
    OTHER = "other", "Other"


class EnquiryRequestType(models.TextChoices):
    AVAILABILITY = "availability", "Availability"
    INFO = "info", "Info"
    QUOTE = "quote", "Quote"
    BROCHURE = "brochure", "Brochure"
    OTHER = "other", "Other"


class EnquiryNoteKind(models.TextChoices):
    GENERAL = "general", "General"
    INTERNAL = "internal", "Internal"
    PREFERENCES = "preferences", "Preferences"


class EnquiryEventKind(models.TextChoices):
    STATUS_CHANGE = "status_change", "Status change"
    ASSIGNED = "assigned", "Assigned"
    UNASSIGNED = "unassigned", "Unassigned"
    CONTACTED = "contacted", "Contacted"
    QUOTE_SENT = "quote_sent", "Quote sent"
    CONVERTED = "converted", "Converted"
    LOST = "lost", "Lost"
    REOPENED = "reopened", "Reopened"
    NOTE_ADDED = "note_added", "Note added"


class QuotationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    ACCEPTED = "accepted", "Accepted"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class BookingStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING_OWNER_APPROVAL = "pending_owner_approval", "Pending owner approval"
    AWAITING_DEPOSIT = "awaiting_deposit", "Awaiting deposit"
    DEPOSIT_PAID = "deposit_paid", "Deposit paid"
    AWAITING_BALANCE = "awaiting_balance", "Awaiting balance"
    BALANCE_PAID = "balance_paid", "Balance paid"
    CHECKED_IN = "checked_in", "Checked in"
    CHECKED_OUT = "checked_out", "Checked out"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"
    DECLINED = "declined", "Declined"


# Active bookings for payment/reminder purposes — money is in flight or
# captured. PENDING_OWNER_APPROVAL is deliberately excluded; no payment is
# due until the owner has approved.
ACTIVE_BOOKING_STATUSES: tuple[str, ...] = (
    BookingStatus.AWAITING_DEPOSIT.value,
    BookingStatus.DEPOSIT_PAID.value,
    BookingStatus.AWAITING_BALANCE.value,
    BookingStatus.BALANCE_PAID.value,
    BookingStatus.CHECKED_IN.value,
)

# States that occupy the date range and must not overlap on the same
# property. Includes PENDING_OWNER_APPROVAL so two owners can't race on
# overlapping approvals (see `booking_no_overlap_blocking` constraint).
OVERLAP_BLOCKING_BOOKING_STATUSES: tuple[str, ...] = (
    BookingStatus.PENDING_OWNER_APPROVAL.value,
    *ACTIVE_BOOKING_STATUSES,
)

TERMINAL_BOOKING_STATUSES: tuple[str, ...] = (
    BookingStatus.CHECKED_OUT.value,
    BookingStatus.CANCELLED.value,
    BookingStatus.EXPIRED.value,
    BookingStatus.DECLINED.value,
)


class BookingNoteKind(models.TextChoices):
    GENERAL = "general", "General"
    INTERNAL = "internal", "Internal"
    CONCIERGE = "concierge", "Concierge"
    VILLA = "villa", "Villa"


class BookingNoteVisibility(models.TextChoices):
    STAFF_ONLY = "staff_only", "Staff only"
    OWNER = "owner", "Owner"
    GUEST = "guest", "Guest"


class BookingHoldReason(models.TextChoices):
    QUOTATION_OPEN = "quotation_open", "Quotation open"
    BOOKING_DEPOSIT_PENDING = "booking_deposit_pending", "Booking deposit pending"
    OWNER_BLOCK = "owner_block", "Owner block"
    MAINTENANCE = "maintenance", "Maintenance"
    MANUAL = "manual", "Manual"


# Reasons an operator may create/edit/remove from the availability calendar.
# Quotation/booking-deposit holds are managed via their source, never here.
OPERATOR_EDITABLE_HOLD_REASONS: tuple[str, ...] = (
    BookingHoldReason.OWNER_BLOCK.value,
    BookingHoldReason.MAINTENANCE.value,
    BookingHoldReason.MANUAL.value,
)


class EventSource(models.TextChoices):
    USER = "user", "User"
    OWNER = "owner", "Owner"
    WEBHOOK = "webhook", "Webhook"
    SYSTEM = "system", "System"
    ADMIN = "admin", "Admin"


class ConciergeTier(models.TextChoices):
    QUINTESSENTIAL = "quintessential", "Quintessential"
    SIGNATURE = "signature", "Signature"


class ConciergeUnit(models.TextChoices):
    DAY = "day", "Day"
    STAY = "stay", "Stay"
    EVENT = "event", "Event"
    HOUR = "hour", "Hour"


class ConciergeStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"
    DELIVERED = "delivered", "Delivered"


class PaymentMethod(models.TextChoices):
    CARD = "card", "Card"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
