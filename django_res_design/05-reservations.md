# 05 — Reservations

The reservation lifecycle: guest captures, enquiries, quotations, bookings, concierge, terms acceptance. Booking state machine details and availability strategy live in `06-availability.md`.

## File layout

```
reservations/
├── enums.py
├── models/
│   ├── __init__.py
│   ├── guest.py        # Guest
│   ├── enquiry.py      # Enquiry, EnquiryNote
│   ├── quotation.py    # Quotation, QuotationLine
│   ├── booking.py      # Booking, BookingHold, BookingEvent, BookingNote
│   ├── concierge.py    # ConciergeService, BookingConciergeItem
│   └── terms.py        # TermsVersion
├── services.py         # QuotationService, BookingService, HoldService
├── signals.py
└── tasks.py            # Celery: expire holds, advance balance-due, send reminders
```

## Guest

### `Guest(SoftDeleteModel)`
Unified entity replacing the legacy `VillaEnquire` form fields + `VillaClientDetail`. Reused across enquiries, quotations, and bookings.

- `first_name`, `last_name` — CharField
- `title` — CharField(blank=True)
- `email` — `CIEmailField(db_index=True)` (case-insensitive via `citext`; **not** unique — same person legitimately books from different addresses)
- `phone` — CharField(blank=True)
- `address_line_1`, `address_line_2` — CharField(blank=True)
- `town`, `post_code` — CharField(blank=True)
- `country` — FK properties.Country PROTECT, null=True
- `contact_method` — TextChoices (`EMAIL`, `PHONE`, `SMS`), null=True
- `marketing_consent` — bool(default=False)
- `notes` — TextField(blank=True)
- `user` — OneToOneField(User, null=True, blank=True, on_delete=SET_NULL) — opportunistic link if guest registers later
- `merged_into` — ForeignKey("self", null=True, blank=True, on_delete=SET_NULL) — set when this guest record is merged into another by an admin
- `legacy_id` — nullable, indexed

Service method: `Guest.merge(target: Guest)` — atomically rewrites FK on Enquiry/Quotation/Booking from self to target, sets `self.merged_into = target`, soft-deletes self.

## Enquiry

### `Enquiry(SoftDeleteModel)`
Anonymous / unstructured inquiry from website or agent. **Kept separate from Quotation** — different shape, different audit needs, different lifecycle. Bridge is `Quotation.enquiry` nullable FK.

- `reference` — CharField(unique=True) — short slug, e.g. `E-2026-000123`
- `guest` — FK Guest SET_NULL, null=True (set once captured; for purely anonymous form submits, hold the form fields below)
- `first_name`, `last_name`, `email`, `phone` — denormalised for anonymous submits
- `property` — FK properties.Property SET_NULL, null=True
- `region` — FK properties.Region SET_NULL, null=True
- `date_from` — DateField(null=True)
- `date_to` — DateField(null=True)
- `is_flexible` — BooleanField(default=False)
- `adults` — PositiveSmallInteger(default=2)
- `children` — PositiveSmallInteger(default=0)
- `min_bedrooms` — PositiveSmallInteger(null=True)
- `request_type` — TextChoices (`AVAILABILITY`, `INFO`, `QUOTE`, `BROCHURE`, `OTHER`)
- `referral_code` — CharField(blank=True)
- `agent` — FK accounts.Contact SET_NULL, null=True
- `site_source` — TextChoices (`MAIN_WEBSITE`, `AGENT_PORTAL`, `EMAIL_INBOUND`, `PHONE`, `OTHER`)
- `status` — TextChoices (`NEW`, `CONTACTED`, `QUOTED`, `LOST`, `CONVERTED`)
- `inbound_message` — TextField(blank=True) — the original message the lead submitted via the public form (single field, write-once at capture, treated as immutable provenance)

Indexes: `(status, created_at)`, `email`, `(property, date_from)`.

Note collection is via `EnquiryNote` (see below). Operator scratchpads (legacy `Notes`, `PreferencesNote`, `internal_notes`) collapse into `EnquiryNote` rows with `kind` discriminator.

When a quotation is created from an enquiry, set `enquiry.status = QUOTED` and `quotation.enquiry = enquiry`. Conversion to a booking sets `enquiry.status = CONVERTED`.

### `EnquiryNote(TimestampedModel)`
Append-able operator notes attached to an enquiry. Replaces the legacy single `VillaEnquire.Notes` and `PreferencesNote` columns, which the legacy Blazor UI rendered as overwrite-only textareas with no authorship or audit.

- `enquiry` — FK Enquiry CASCADE
- `author` — FK User SET_NULL, null=True
- `kind` — TextChoices (`GENERAL`, `INTERNAL`, `PREFERENCES`)  # `GENERAL` is the customer-facing scratchpad; `INTERNAL` is the back-office-only counterpart; `PREFERENCES` carries the legacy `PreferencesNote` content
- `body` — TextField  # rich text / markdown; renderer determined client-side
- `is_pinned` — bool(default=False)  # optional, pins to top of timeline view

Indexes: `(enquiry, created_at)`.

Ordering: `created_at` ascending. Editing rewrites the same row (PATCH); deletion is hard (no soft-delete — the audit lives in `AuditLog`).

## Quotation

### `Quotation(SoftDeleteModel)`
- `reference` — CharField(unique) — `Q-2026-000123`
- `enquiry` — FK Enquiry SET_NULL, null=True (quotations can be created agent-direct without an enquiry)
- `guest` — FK Guest PROTECT — required (anonymous must convert to a Guest before quoting)
- `agent` — FK accounts.Contact PROTECT, null=True
- `currency` — FK pricing.Currency PROTECT
- `is_unbranded` — bool(default=False)  # legacy concept retained
- `status` — TextChoices (`DRAFT`, `SENT`, `ACCEPTED`, `EXPIRED`, `CANCELLED`)
- `expires_at` — DateTimeField
- `terms_version` — FK TermsVersion PROTECT

Quotation-level notes are reached through the source `Enquiry` (via `EnquiryNote`) and the destination `Booking` (via `BookingNote`). The header carries no free-text columns — operators add commentary on the enquiry before the quote is sent and on the booking after it converts. Per-line operator notes are still allowed (`QuotationLine.notes` below) because they are scoped to one option in a multi-villa quote.

Transitions: `send()` (DRAFT→SENT, sets `expires_at` if null), `accept(line)` (SENT→ACCEPTED, marks one line `is_selected=True`, triggers Booking creation), `expire()` (Celery), `cancel(reason)`.

### `QuotationLine(SoftDeleteModel)`
One quotation can present 1–N villas as options.
- `quotation` — FK CASCADE
- `property` — FK properties.Property PROTECT
- `date_from`, `date_to` — DateField
- `adults`, `children` — PositiveSmallInteger
- `pricing_snapshot` — JSONField  # the full `Quote.breakdown` from PricingEngine
- `total` — Decimal(12, 2)  # extracted for query convenience
- `is_selected` — bool(default=False)  # set when accepted
- `is_manual` — bool(default=False)  # admin overrode the engine
- `notes` — TextField(blank=True)

Constraint: `CheckConstraint(date_from < date_to)`. `UniqueConstraint(quotation, condition=Q(is_selected=True), name="one_selected_line_per_quotation")`.

## Booking

### `Booking(SoftDeleteModel)`
The reservation. Proper FK to the source `QuotationLine`, with the price locked at creation by snapshotting `pricing_snapshot`.

- `reference` — CharField(unique) — `B-2026-000123`
- `quotation_line` — FK QuotationLine PROTECT  # real FK, not the legacy integer `QuotationNo`
- `guest` — FK Guest PROTECT
- `property` — FK properties.Property PROTECT  # denormalised from quotation_line for query speed; enforced equal in clean()
- `date_from`, `date_to` — DateField
- `adults`, `children` — PositiveSmallInteger
- `currency` — FK pricing.Currency PROTECT
- `pricing_snapshot` — JSONField  # **copied from QuotationLine at creation, never recomputed**
- `rental_price` — Decimal(12, 2)  # extracted for reports
- `deposit_amount` — Decimal(12, 2)
- `deposit_percentage` — Decimal(5, 2, null=True)
- `discount` — Decimal(12, 2, default=0)
- `adjustment` — Decimal(12, 2, default=0)  # one-off line item (concierge total feeds in here)
- `balance_due` — Decimal(12, 2)  # computed at creation
- `balance_due_at` — DateField  # derived from PaymentSchedule
- `status` — TextChoices (see 06-availability.md for full machine)
- `agent` — FK accounts.Contact SET_NULL, null=True
- `site_source` — TextChoices (mirror Enquiry.site_source)
- `terms_version` — FK TermsVersion PROTECT
- `terms_accepted_at` — DateTimeField
- `payment_method` — TextChoices (`CARD`, `BANK_TRANSFER`)
- `cancel_reason` — TextField(blank=True)
- `cancelled_at` — DateTimeField(null=True, blank=True)
- `legacy_id` — nullable, indexed

Indexes: `(property, status, date_from)`, `(status, balance_due_at)`, `reference`.

Constraints:
- `CheckConstraint(date_from < date_to)`
- Postgres `EXCLUDE USING gist` on `(property_id WITH =, daterange(date_from, date_to, '[)') WITH &&) WHERE status IN ('awaiting_deposit', 'deposit_paid', 'awaiting_balance', 'balance_paid', 'checked_in')` — DB-level double-booking prevention for active states.

### `BookingEvent(TimestampedModel)`
Append-only state-machine audit. Replaces the drifting `VillaArchiveBooking`.
- `booking` — FK Booking PROTECT
- `from_status`, `to_status` — TextChoices
- `actor` — FK User SET_NULL, null=True
- `source` — TextChoices (`USER`, `OWNER`, `WEBHOOK`, `SYSTEM`, `ADMIN`)
- `reason` — CharField(blank=True)
- `meta` — JSONField(default=dict)

Booking history is `events.order_by('created_at')` — no drift, full provenance.

### `BookingNote(TimestampedModel)`
Append-able operator notes attached to a booking. Replaces the legacy single `VillaBooking.Notes`, `ConciergeNotes`, and the "Customer Notes (Internal)" / "Booking summary information" / "Internal booking information" textareas that the legacy Blazor `Booking.razor` page bound to flat columns with no authorship.

- `booking` — FK Booking CASCADE
- `author` — FK User SET_NULL, null=True
- `kind` — TextChoices (`GENERAL`, `INTERNAL`, `CONCIERGE`, `VILLA`)  # `GENERAL` ≈ legacy "Notes" / booking summary; `INTERNAL` ≈ legacy "Internal booking information"; `CONCIERGE` ≈ legacy `ConciergeNotes`; `VILLA` is the property-manager-visible operations note carried over from the original "Villa notes" textarea
- `body` — TextField  # rich text / markdown
- `is_pinned` — bool(default=False)
- `visibility` — TextChoices (`STAFF_ONLY`, `OWNER`, `GUEST`)  # gates who sees the note on portals / docs; `STAFF_ONLY` is the default

Indexes: `(booking, created_at)`, `(booking, kind)`.

Ordering: `created_at` ascending. Editing rewrites the same row (PATCH); deletion is hard. The full mutation audit lives in `AuditLog`.

### `BookingHold`
Lives here logically but documented in 06-availability.md.

## Concierge

### `ConciergeService(SoftDeleteModel)`
Catalogue, can be property-scoped or global.
- `property` — FK Property CASCADE, null=True (global if null)
- `name`, `description`
- `cost_per_unit` — Decimal(12, 2)
- `unit` — TextChoices (`DAY`, `STAY`, `EVENT`, `HOUR`)
- `currency` — FK Currency PROTECT
- `is_active` — bool

### `BookingConciergeItem(SoftDeleteModel)`
- `booking` — FK CASCADE
- `service` — FK ConciergeService PROTECT
- `quantity` — PositiveSmallInteger
- `unit_price_snapshot` — Decimal(12, 2)  # locked at add time
- `currency_snapshot` — CharField(3)
- `status` — TextChoices (`REQUESTED`, `CONFIRMED`, `CANCELLED`, `DELIVERED`)
- `notes` — TextField(blank=True)

Aggregation feeds `Booking.adjustment` via signal on save/delete.

## Terms

### `TermsVersion(TimestampedModel)`
Append-only legal copy versions.
- `version` — CharField(unique)  # e.g. "2026-01"
- `published_at` — DateTimeField
- `body_markdown` — TextField
- `is_current` — bool(unique constraint with condition `is_current=True`)

Both `Quotation.terms_version` and `Booking.terms_version` snapshot the version active at creation.

## Services

- `QuotationService.create_from_enquiry(enquiry, lines: list[dict]) -> Quotation` — builds Quotation + QuotationLines, runs PricingEngine per line, snapshots, places a `BookingHold` for each villa+date pair while quotation is open (`expires_at = quotation.expires_at`).
- `BookingService.create_from_quotation_line(quotation_line, terms_version, payment_method, ...) -> Booking` — copies `pricing_snapshot`, computes `balance_due` and `balance_due_at` via effective PaymentSchedule, sets initial status `PENDING_OWNER_APPROVAL` or `AWAITING_DEPOSIT` per property config, releases competing holds, writes `BookingEvent`.
- `HoldService` — see 06.
- All transition methods on Booking (`submit`, `owner_approve`, `record_deposit`, `record_balance`, `check_in`, `complete`, `cancel`) wrap state mutation + event row + signal in `transaction.atomic`.

## Signals

- `booking_transitioned(booking, from_status, to_status, actor, source)` — fired by every transition method.
- `payments.payment_succeeded` (from payments app) is **received** here; handler calls the matching booking transition (`record_deposit` or `record_balance` based on `payment.purpose`).

## Dropped from legacy

- `VillaArchiveBooking` — replaced by `Booking.status='COMPLETED'` plus `BookingEvent` history.
- `VillaCheckoutDetail` — its fields scatter across `Booking`, `Guest`, and `Payment`. No separate entity; the checkout-page form posts to multiple endpoints.
- `IsActive`, `Tbc` booleans on Booking — collapsed into `status`.
- `IsOwnerConfirmed`, `IsDepositePaid`, `IsBankPaid` booleans — collapsed into `status`.
- `BookingUrl` — generated on demand via `reverse()`, not stored.
- Email link tracking / code sent history — out of scope here; lives in a future `comms` app if needed.
