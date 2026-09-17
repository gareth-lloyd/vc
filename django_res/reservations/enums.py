"""TextChoices used across the reservations app.

Kept flat in one module to make the closed sets easy to scan and reuse.
"""

from __future__ import annotations

from django.db import models


class ContactMethod(models.TextChoices):
    EMAIL = "email", "Email"
    PHONE = "phone", "Phone"
    SMS = "sms", "SMS"


class EnquiryStatus(models.TextChoices):
    # Stage vocabulary mirrors the operator-facing dashboard (GAP-038/039):
    # progressing / quote_sent / dead were formerly contacted / quoted / lost.
    NEW = "new", "New"
    PROGRESSING = "progressing", "Progressing"
    QUOTE_SENT = "quote_sent", "Quote sent"
    FOLLOW_UP = "follow_up", "Follow-up"
    DEAD = "dead", "Dead"
    CONVERTED = "converted", "Converted"


# Allowed Enquiry transitions, enforced by `Enquiry._transition` via
# `core.transitions`. DEAD can be reopened; CONVERTED is final.
ENQUIRY_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    EnquiryStatus.NEW.value: frozenset(
        {
            EnquiryStatus.PROGRESSING.value,
            EnquiryStatus.QUOTE_SENT.value,
            EnquiryStatus.DEAD.value,
        }
    ),
    EnquiryStatus.PROGRESSING.value: frozenset(
        {
            EnquiryStatus.QUOTE_SENT.value,
            EnquiryStatus.FOLLOW_UP.value,
            EnquiryStatus.CONVERTED.value,
            EnquiryStatus.DEAD.value,
        }
    ),
    EnquiryStatus.QUOTE_SENT.value: frozenset(
        {
            EnquiryStatus.FOLLOW_UP.value,
            EnquiryStatus.CONVERTED.value,
            EnquiryStatus.DEAD.value,
        }
    ),
    EnquiryStatus.FOLLOW_UP.value: frozenset(
        {
            EnquiryStatus.QUOTE_SENT.value,
            EnquiryStatus.CONVERTED.value,
            EnquiryStatus.DEAD.value,
        }
    ),
    EnquiryStatus.DEAD.value: frozenset({EnquiryStatus.NEW.value}),
    EnquiryStatus.CONVERTED.value: frozenset(),
}


class LeadStatus(models.TextChoices):
    """Lead temperature — a subjective sales signal the operator sets directly,
    orthogonal to the workflow `EnquiryStatus`. New in the rebuild (legacy had
    no lead-quality field); pushed to Zoho as a CRM tag."""

    HOT = "hot", "Hot"
    WARM = "warm", "Warm"
    COLD = "cold", "Cold"
    DEAD = "dead", "Dead"


class EnquiryLostReason(models.TextChoices):
    """Why a dead enquiry was lost. Required whenever status is DEAD; the
    `enquiry_dead_requires_lost_reason` constraint enforces non-empty."""

    FOUND_ALTERNATIVE = "found_alternative", "Found alternative"
    AVAILABILITY = "availability", "Availability"
    DIFFERENT_DESTINATION = "different_destination", "Different destination"
    NO_GROUP_CONSENSUS = "no_group_consensus", "No group consensus"
    UNKNOWN = "unknown", "Unknown"


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
    FOLLOW_UP = "follow_up", "Follow-up"
    CONVERTED = "converted", "Converted"
    LOST = "lost", "Lost"
    REOPENED = "reopened", "Reopened"
    NOTE_ADDED = "note_added", "Note added"
    LEAD_STATUS_CHANGED = "lead_status_changed", "Lead status changed"


class QuotationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    ACCEPTED = "accepted", "Accepted"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


# Allowed Quotation transitions, enforced via `core.transitions` by
# `Quotation.accept`/`expire`/`cancel` and `record_quote_sent` (DRAFT → SENT).
# Editability (`_MUTABLE_QUOTATION_STATUSES`) is a separate rule, not this table.
QUOTATION_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    QuotationStatus.DRAFT.value: frozenset(
        {
            QuotationStatus.SENT.value,
            QuotationStatus.EXPIRED.value,
            QuotationStatus.CANCELLED.value,
        }
    ),
    QuotationStatus.SENT.value: frozenset(
        {
            QuotationStatus.ACCEPTED.value,
            QuotationStatus.EXPIRED.value,
            QuotationStatus.CANCELLED.value,
        }
    ),
    QuotationStatus.ACCEPTED.value: frozenset(),
    QuotationStatus.EXPIRED.value: frozenset(),
    QuotationStatus.CANCELLED.value: frozenset(),
}


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

# Statuses a booking can only hold after entering AWAITING_DEPOSIT — i.e.
# after confirmation, when the contract is issued and the house rules are
# snapshotted (GAP-094). `Booking.has_been_confirmed()` is the predicate:
# these answer without a query; CANCELLED / EXPIRED / DECLINED need the
# event trail.
CONFIRMED_BOOKING_STATUSES: frozenset[str] = frozenset(
    (*ACTIVE_BOOKING_STATUSES, BookingStatus.CHECKED_OUT.value)
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

# Allowed Booking transitions, enforced by `Booking._transition` via
# `core.transitions`. Every live status can still be cancelled.
BOOKING_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    BookingStatus.DRAFT.value: frozenset(
        {
            BookingStatus.PENDING_OWNER_APPROVAL.value,
            BookingStatus.AWAITING_DEPOSIT.value,
            BookingStatus.CANCELLED.value,
        }
    ),
    BookingStatus.PENDING_OWNER_APPROVAL.value: frozenset(
        {
            BookingStatus.AWAITING_DEPOSIT.value,
            BookingStatus.DECLINED.value,
            BookingStatus.CANCELLED.value,
        }
    ),
    BookingStatus.AWAITING_DEPOSIT.value: frozenset(
        {
            BookingStatus.DEPOSIT_PAID.value,
            BookingStatus.EXPIRED.value,
            BookingStatus.CANCELLED.value,
        }
    ),
    BookingStatus.DEPOSIT_PAID.value: frozenset(
        {
            BookingStatus.AWAITING_BALANCE.value,
            BookingStatus.BALANCE_PAID.value,
            BookingStatus.CANCELLED.value,
        }
    ),
    BookingStatus.AWAITING_BALANCE.value: frozenset(
        {BookingStatus.BALANCE_PAID.value, BookingStatus.CANCELLED.value}
    ),
    BookingStatus.BALANCE_PAID.value: frozenset(
        {BookingStatus.CHECKED_IN.value, BookingStatus.CANCELLED.value}
    ),
    BookingStatus.CHECKED_IN.value: frozenset(
        {BookingStatus.CHECKED_OUT.value, BookingStatus.CANCELLED.value}
    ),
    **{status: frozenset() for status in TERMINAL_BOOKING_STATUSES},
}

# Status gates for the Clients-directory region aggregation (GAP-047).
#
# A region is *quoted* once a real quote has been sent (SENT/ACCEPTED; excludes
# DRAFT/EXPIRED/CANCELLED). Legacy quotes load DRAFT or EXPIRED and the
# migration's synthesised `booking-` fills (ACCEPTED) are excluded by the
# aggregation, so legacy clients' quoted regions stay empty; quotes accrue
# going forward.
QUOTED_STATUSES: tuple[str, ...] = (
    QuotationStatus.SENT.value,
    QuotationStatus.ACCEPTED.value,
)

# A region is *booked* for any reservation that wasn't cancelled/expired/declined
# — i.e. everything that actually occupied (or will occupy) the dates. This
# mirrors `Booking.occupying()`'s "exclude terminal" philosophy but is expressed
# as an exclusion so it INCLUDES the legacy book of business: the migration rests
# imported reservations at DRAFT (`data_migration.loaders.bookings`), and a
# positive ACTIVE-only list would silently blank booked regions for every
# migrated client. CHECKED_OUT (a completed stay) is kept — a past stay is still
# a booked region.
UNREALISED_BOOKING_STATUSES: tuple[str, ...] = (
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
    OWNER_BLOCK = "owner_block", "Owner block"
    MAINTENANCE = "maintenance", "Maintenance"
    MANUAL = "manual", "Manual"


# Reasons an operator may create/edit/remove from the availability calendar.
# Quotation holds are managed via their source (the quotation), never here.
OPERATOR_EDITABLE_HOLD_REASONS: tuple[str, ...] = (
    BookingHoldReason.OWNER_BLOCK.value,
    BookingHoldReason.MAINTENANCE.value,
    BookingHoldReason.MANUAL.value,
)


class OwnerBlockKind(models.TextChoices):
    """Why an owner wants to block their villa's availability."""

    OWNER_STAY = "owner_stay", "Owner stay"
    MAINTENANCE = "maintenance", "Maintenance"
    OTHER = "other", "Other"


class OwnerBlockStatus(models.TextChoices):
    """Lifecycle of an owner availability block.

    A block is APPROVED the moment it is created — the indefinite `BookingHold`
    is placed up front, so the block occupies the calendar immediately. The
    owner may CANCEL it, which releases the hold. No soft delete; the enum is
    the lifecycle.
    """

    APPROVED = "approved", "Approved"
    CANCELLED = "cancelled", "Cancelled"


class OwnerBlockSource(models.TextChoices):
    """How an owner block came to exist.

    MANUAL blocks are created by a staff/owner action and carry a `created_by`.
    ICAL blocks are imported by the calendar-feed poller (GAP-011); they have no
    human creator (`created_by` is null) and are reconciled against the feed.
    """

    MANUAL = "manual", "Manual"
    ICAL = "ical", "iCal feed"


class OwnerBlockUpdateKind(models.TextChoices):
    """The change event surfaced in the staff owner-block feed."""

    CREATED = "created", "Created"
    CANCELLED = "cancelled", "Cancelled"


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


class ConciergeService(models.TextChoices):
    """Fixed service columns of the concierge coverage matrix (mock-up 01).

    Values mirror the frontend `ServiceKey` palette in `styles/tokens.ts`.
    """

    CAR = "car", "Car hire"
    TRANSFERS = "transfers", "Transfers"
    BOAT = "boat", "Boat"
    CHEF = "chef", "Chef"
    GROCERY = "grocery", "Grocery"
    FIRSTNIGHT = "firstnight", "First night"
    RESTAURANT = "restaurant", "Restaurant"
    GIFTING = "gifting", "Gifting"
    ACTIVITIES = "activities", "Activities"
    SPA = "spa", "Spa"
    WINE = "wine", "Wine"
    NANNY = "nanny", "Nanny"
    OTHER = "other", "Other"


class ServiceStatus(models.TextChoices):
    """Per-service progress state in the coverage matrix.

    Mirrors the frontend `SERVICE_STATUSES` in `components/data/ServiceDot.tsx`.
    `NOT_REQUIRED` rows are excluded from the progress denominator.
    """

    NOT_STARTED = "not_started", "Not started"
    WORKING_ON_IT = "working_on_it", "Working on it"
    WAITING = "waiting", "Waiting"
    ARRANGED_INDEPENDENTLY = "arranged_independently", "Arranged independently"
    NOT_REQUIRED = "not_required", "Not required"
    DONE = "done", "Done"


class PaymentMethod(models.TextChoices):
    CARD = "card", "Card"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"


class DamageClaimStatus(models.TextChoices):
    """Lifecycle of a damages claim raised against a booking's security deposit.

    A claim is OPEN when filed, APPROVED once an operator signs off the
    deduction, SETTLED once the deposit has been captured against it, and
    WITHDRAWN if dropped. The enforced state machine (approval gating, the
    threshold permissions, the guest-acceptance flow) lands with workflow 8;
    v1 ships the field + default so the lifecycle has somewhere to live and the
    audit trail captures status moves.
    """

    OPEN = "open", "Open"
    APPROVED = "approved", "Approved"
    SETTLED = "settled", "Settled"
    WITHDRAWN = "withdrawn", "Withdrawn"


class BookingGuestRole(models.TextChoices):
    """Role a guest plays on a Booking via the BookingGuest through-model.

    - LEAD: primary guest — exactly one per booking. Mirrored on
      `Booking.person` (denormalised pointer kept in sync via signal).
    - CO_TRAVELLER: additional party member; zero-or-more per booking.
    - PAYER: party paying for the stay if not the lead; at most one per
      booking.
    - CC_ONLY: copy on comms; not part of the travelling party.
    """

    LEAD = "lead", "Lead"
    CO_TRAVELLER = "co_traveller", "Co-traveller"
    PAYER = "payer", "Payer"
    CC_ONLY = "cc_only", "CC only"


class ChargeCategory(models.TextChoices):
    """Reporting taxonomy for manual `BookingChargeItem` lines (GAP-088).

    Superset of `pricing.enums.ExtraKind`: the shared values are verbatim
    copies (same strings and labels — pinned by test) so quote-time extras and
    manual charge lines present ONE vocabulary to Zoho, plus the charge-only
    concepts (`damage`, `credit`) that never occur at quote time. The
    free-text `label` stays alongside for detail.
    """

    CLEANING = "cleaning", "Cleaning"
    PET_FEE = "pet_fee", "Pet fee"
    HEATING = "heating", "Heating"
    LINEN = "linen", "Linen"
    EXTRA_BED = "extra_bed", "Extra bed"
    SERVICE_FEE = "service_fee", "Service fee"
    RESORT_FEE = "resort_fee", "Resort fee"
    DAMAGE = "damage", "Damage"
    CREDIT = "credit", "Credit"
    OTHER = "other", "Other"


class BookingDocumentKind(models.TextChoices):
    """Guest-facing documents a booking can carry (GAP-094).

    The full set the API spec names, so the vocabulary is stable from day one
    — but only `CONTRACT` is generatable today; the render seam refuses the
    rest with `UnsupportedDocumentKind`.
    """

    CONFIRMATION = "confirmation", "Confirmation"
    CONTRACT = "contract", "Contract"
    VOUCHER = "voucher", "Voucher"
    INVOICE = "invoice", "Invoice"
    RECEIPT = "receipt", "Receipt"
