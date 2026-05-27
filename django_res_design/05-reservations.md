# 05 — Reservations

The reservation lifecycle: guest captures, enquiries, quotations, bookings, concierge, terms acceptance. Booking state machine details and availability strategy live in `06-availability.md`.

## File layout

```
reservations/
├── enums.py
├── models/
│   ├── __init__.py
│   ├── guest.py        # Guest
│   ├── enquiry.py      # Enquiry, EnquiryNote, EnquiryEvent
│   ├── preferences.py  # GuestPreferenceType, GuestPreference
│   ├── quotation.py    # Quotation, QuotationLine
│   ├── booking.py      # Booking, BookingHold, BookingEvent, BookingNote
│   ├── concierge.py    # BookingConciergeItem
│   └── terms.py        # TermsVersion
├── services.py         # QuotationService, BookingService, HoldService
├── signals.py
└── tasks.py            # Celery: expire holds, advance balance-due, send reminders
```

## Guest

### `Guest(AuditedModel)`
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
- `status` — TextChoices (`ACTIVE`, `ARCHIVED`, `ANONYMIZED`), default `ACTIVE`
- `anonymized_at` — DateTimeField(null=True, blank=True) — set by `anonymize()`
- `user` — OneToOneField(User, null=True, blank=True, on_delete=SET_NULL) — opportunistic link if guest registers later
- `legacy_id` — nullable, indexed

Indexes: `(status, last_name, first_name)`, `email`.

#### Lifecycle (per `00-conventions.md`)

- **Wrong guest captured, no relationships yet** — hard delete.
- **Guest no longer relevant but bookings exist** — set `status=ARCHIVED`. Still queryable; hidden from default operator search only by an explicit `?status=` filter at the call site, not a hidden manager.
- **`Guest.merge(target: Guest)`** — destructive. Atomically rewrites FKs on `Enquiry`, `Quotation`, `Booking` (and any `BookingConciergeItem` reached via `Booking`) from `self` to `target`. Writes one `AuditLog` row per rewrite. Then **hard-deletes** `self`. There is no `merged_into` self-FK and no surviving tombstone — the `AuditLog` is the only trail.
- **`Guest.anonymize()`** — overwrites `first_name`, `last_name`, `email` (replaced with `"redacted-{id}@anonymized.local"`), `phone` (empty), `address_line_1`, `address_line_2`, `town`, `post_code`, `notes`; clears `marketing_consent`; sets `status=ANONYMIZED`, `anonymized_at=now()`. Bookings retain the FK pointing at the anonymized row. Reporting that should exclude anonymized guests filters `status` explicitly.

### `GuestPreferenceType(TimestampedModel)`
Operator-curated catalogue of guest preferences (legacy `VillaClientPrefMaster` — bed configurations, dietary, etc.).

- `name` — CharField(unique=True)
- `is_active` — bool(default=True)
- `legacy_id` — nullable, indexed

### `GuestPreference(TimestampedModel)`
A typed preference attached to a guest, optionally scoped to a quotation when captured during quoting.

- `guest` — FK Guest CASCADE, `related_name="preferences"`
- `preference_type` — FK GuestPreferenceType PROTECT
- `quotation` — FK Quotation SET_NULL, null=True, blank=True, `related_name="guest_preferences"`
- `notes` — TextField(blank=True)
- `legacy_id` — nullable, indexed

Constraints: `UniqueConstraint(guest, preference_type, quotation)`.

## Enquiry

### `Enquiry(AuditedModel)`
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
- `agent` — FK accounts.Contact SET_NULL, null=True  # external agent / intermediary representing the guest; distinct from `assigned_to`
- `assigned_to` — FK User SET_NULL, null=True, blank=True, related_name="assigned_enquiries"  # internal staff owner of this enquiry, backing `?assigned_to=` filter and `:assign` action. Separate from `agent`: `agent` is who is *acting on behalf of the guest*; `assigned_to` is *which staff member owns the work*. See reconciliation issue #26.
- `site_source` — TextChoices (`MAIN_WEBSITE`, `AGENT_PORTAL`, `EMAIL_INBOUND`, `PHONE`, `OTHER`)
- `status` — TextChoices (`NEW`, `CONTACTED`, `QUOTED`, `LOST`, `CONVERTED`)
- `inbound_message` — TextField(blank=True) — the original message the lead submitted via the public form (single field, write-once at capture, treated as immutable provenance)

Indexes: `(status, created_at)`, `email`, `(property, date_from)`.

Note collection is via `EnquiryNote` (see below). Operator scratchpads (legacy `Notes`, `PreferencesNote`, `internal_notes`) collapse into `EnquiryNote` rows with `kind` discriminator.

When a quotation is created from an enquiry, set `enquiry.status = QUOTED` and `quotation.enquiry = enquiry`. Conversion to a booking sets `enquiry.status = CONVERTED`.

#### Quote stack

One enquiry typically accumulates **multiple `Quotation` rows** over its lifetime — mid-single-digits is common, double-digits not unusual on long-cycle inquiries (per scoping-session 2026-05-26 with the site owner). The data shape already supports this via `Quotation.enquiry` FK; the conversion semantics are:

- **Conversion is measured per `Enquiry`, not per `Quotation`.** As soon as any child `Quotation.status` flips to `ACCEPTED`, the parent `Enquiry.status` transitions to `CONVERTED`. Reporting that quotes a "conversion rate" counts enquiries, not quotes. See decisions row "Conversion is measured per `Enquiry`, not per `Quotation`" in `10-decisions.md`.
- **Staff UI groups every quote under the parent enquiry.** Re-quoting is the default operator action on an open enquiry — a single ordered list (most recent first), with the most recent expanded by default. There is no separate top-level "quote-bundle" entity; the FK is enough.
- **Quote reference numbers stay independent.** `Q-2026-000123` increments globally, not within an enquiry. Grouping is via the FK, not a derived prefix.

#### Date-spread heuristic on intake

Inquiry-takers routinely widen the requested date range by one or two days either side of the client's stated dates, because most guests are flexible around changeover days (typically Saturday, sometimes Sunday or Monday). This is a **judgement call** by the staff member, not a system rule — `Enquiry.date_from` / `date_to` capture whatever the operator chose to record. The intake UI should make it cheap to expand the captured range without re-typing (a "± n days" affordance on the form is the obvious shape). `Enquiry.is_flexible=True` is reserved for when the client *explicitly* said they are flexible; the heuristic above is applied by the operator even when `is_flexible=False`.

The legacy `EnquireDateTypeString` field (`SpecificDays` / `ThreeDays` / `SevenDays` / `WholeDays`) encoded this preset-style at the column level. The new design **drops the encoding** in favour of an open date range plus the heuristic above — the encoding never carried operator-meaningful information after capture. See `workflows/07-enquiry/enquiry-intake.md` for the operator-side detail.

### `EnquiryNote(TimestampedModel)`
Append-able operator notes attached to an enquiry. Replaces the legacy single `VillaEnquire.Notes` and `PreferencesNote` columns, which the legacy Blazor UI rendered as overwrite-only textareas with no authorship or audit.

- `enquiry` — FK Enquiry CASCADE
- `author` — FK User SET_NULL, null=True
- `kind` — TextChoices (`GENERAL`, `INTERNAL`, `PREFERENCES`)  # `GENERAL` is the customer-facing scratchpad; `INTERNAL` is the back-office-only counterpart; `PREFERENCES` carries the legacy `PreferencesNote` content
- `body` — TextField  # rich text / markdown; renderer determined client-side
- `is_pinned` — bool(default=False)  # optional, pins to top of timeline view

Indexes: `(enquiry, created_at)`.

Ordering: `created_at` ascending. Editing rewrites the same row (PATCH); deletion is hard. The mutation audit lives in `AuditLog`.

### `EnquiryEvent(TimestampedModel)`
Append-only state-machine audit on `Enquiry`. Mirrors `BookingEvent`: it is a domain-specific timeline for hot-read paths (the `/enquiries/{id}/activity` endpoint, the enquiry-detail UI's history tab) where structured queries (`from_status`, `to_status`, `actor`) matter and a generic `AuditLog` scan would be too coarse. The cross-cutting `AuditLog` continues to record field-level edits (notes, contact info, assignment changes) for compliance; `EnquiryEvent` records the workflow-state and assignment timeline.

- `enquiry` — FK Enquiry PROTECT
- `from_status`, `to_status` — TextChoices (mirror `Enquiry.status`); equal when the event is non-transitional (e.g. assignment change, note-added flag, manual `:reopen` from `LOST` back to a prior status)
- `kind` — TextChoices (`STATUS_CHANGE`, `ASSIGNED`, `UNASSIGNED`, `CONTACTED`, `QUOTE_SENT`, `CONVERTED`, `LOST`, `REOPENED`, `NOTE_ADDED`) — keeps the activity stream queryable without parsing free-text reasons
- `actor` — FK User SET_NULL, null=True
- `source` — TextChoices (`USER`, `OWNER`, `WEBHOOK`, `SYSTEM`, `ADMIN`)
- `reason` — CharField(blank=True)
- `meta` — JSONField(default=dict)  # e.g. `{"assignee_from": 12, "assignee_to": 34}` for assignment changes; `{"quotation_id": 99}` for `QUOTE_SENT`

Indexes: `(enquiry, created_at)`.

Enquiry history is `events.order_by('created_at')` — same pattern as `BookingEvent`. Every transition method on `Enquiry` (`contact()`, `quote_sent()`, `assign(user)`, `convert()`, `lose(reason)`, `reopen()`) writes one row in the same `transaction.atomic` block. `NOTE_ADDED` is the only event-kind written outside a transition method — emitted by an `EnquiryNote.post_save` signal so the activity timeline shows note authorship inline with status changes.

See reconciliation issue #27.

## Quotation

### `Quotation(AuditedModel)`
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

### `QuotationLine(AuditedModel)`
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

### `Booking(AuditedModel)`
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
- `discount` — Decimal(12, 2, default=0)
- `adjustment` — Decimal(12, 2, default=0)  # one-off line item (concierge total feeds in here)
- `balance_due` — Decimal(12, 2)  # computed at creation
- `balance_due_at` — DateField  # derived from PaymentSchedule
- `status` — TextChoices (see 06-availability.md for full machine)
- `agent` — FK accounts.Contact SET_NULL, null=True  # external agent / intermediary; same distinction as Enquiry.agent
- `assigned_to` — FK User SET_NULL, null=True, blank=True, related_name="assigned_bookings"  # internal staff owner of this booking, backing `?assigned_to=` filter and `:assign` action. See reconciliation issue #26.
- `site_source` — TextChoices (mirror Enquiry.site_source)
- `terms_version` — FK TermsVersion PROTECT
- `terms_accepted_at` — DateTimeField
- `payment_method` — TextChoices (`CARD`, `BANK_TRANSFER`)
- `cancel_reason` — TextField(blank=True)
- `cancelled_at` — DateTimeField(null=True, blank=True)
- `is_archived` — bool(default=False)  # operator-facing "tidy out of main list" flag. Orthogonal to `status` — a terminal-state booking can be archived without changing its status. Only meaningful in terminal states. See state machine in `06-availability.md` for `archive()`/`restore()` semantics.
- `archived_at` — DateTimeField(null=True, blank=True)
- `legacy_id` — nullable, indexed

Indexes: `(property, status, date_from)`, `(status, balance_due_at)`, `reference`.

Constraints:
- `CheckConstraint(date_from < date_to)`
- Postgres `EXCLUDE USING gist` on `(property_id WITH =, daterange(date_from, date_to, '[)') WITH &&) WHERE status IN ('awaiting_deposit', 'deposit_paid', 'awaiting_balance', 'balance_paid', 'checked_in')` — DB-level double-booking prevention for active states.

#### Deposit fields — single source of truth

The legacy `VillaBooking.DepositAmount` / `DepositPercentage` columns are **not ported.** The deposit lives in two consistent places, neither of them on `Booking`:

- **Deposit policy (config)** — `PropertyFinance.deposit_required` / `deposit_calculation_type` / `deposit_amount` (per `03-finance-config.md`). What the property charges. Read at booking-creation time by `payments.PaymentScheduler.create_for_booking()`.
- **Deposit track (workflow + ledger)** — the `Payment(purpose=DEPOSIT)` row created by `PaymentScheduler` at booking-creation time. What this booking actually owes / has paid. `Payment.amount` is the deposit money figure; `Payment.status` is its lifecycle; the rendered booking-detail view reads from this row for deposit-state display.

The API does not expose a denormalised `deposit_amount` on `Booking`. Consumers needing "the deposit row" hit `GET /bookings/{id}/deposit` (already specified in §2.10 of the API surface) or `GET /payments?booking=…&purpose=DEPOSIT`. The amount is also embedded inside `Booking.pricing_snapshot` (the locked-at-creation JSON breakdown), which is the immutable record of what the deposit was at the moment of confirmation — but the operational source of truth for "what is owed / what is paid" remains the `Payment(purpose=DEPOSIT)` row. See reconciliation issue #45.

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

### `BookingGuest(AuditedModel)`

Through-model linking a `Booking` to the `Guest` rows involved with it. Replaces the legacy single-`Booking.guest` shape that captured the lead traveller and dropped everyone else into free-text notes. Every person the agent CC'd, the family member on the trip, the PA who organised the booking, the third-party payer — all become addressable `Guest` rows, retained for marketing and future-booking continuity. (Per scoping-session 2026-05-26: a decade of CC'd family contacts have been lost under the legacy model.)

Links to `reservations.Guest`, **not** `accounts.Contact`. `Contact` is the operator-side CRM model (owners, managers, agents); `Guest` is the booking-side person model (with `marketing_consent`, opportunistic `user` OneToOne, etc.). The split stays.

- `booking` — FK Booking CASCADE
- `guest` — FK Guest PROTECT
- `role` — TextChoices (`LEAD`, `CO_TRAVELLER`, `PAYER`, `CC_ONLY`)
- `email_override` — `CIEmailField(blank=True)` — when set, transactional emails directed at this `(booking, guest, role)` go here instead of `guest.email`. Lets agents capture a per-trip email (a wedding planner's address, an assistant's address) without polluting the guest's standing email.
- `notes` — TextField(blank=True)

Constraints:
- `UniqueConstraint(booking, guest, role, name="unique_booking_guest_role")` — one role per `(booking, guest)`; a single person can hold multiple roles per booking (e.g. LEAD + PAYER) but each only once.
- `UniqueConstraint(booking, condition=Q(role="LEAD"), name="one_lead_per_booking")` — exactly one LEAD.
- `UniqueConstraint(booking, condition=Q(role="PAYER"), name="at_most_one_payer_per_booking")` — at most one PAYER (zero is allowed when the LEAD also pays).

Indexes: `(booking, role)`, `guest`.

#### Role semantics

- `LEAD` — the primary traveller; the booking's "host". Required on every booking. Carries the address / preferences that previously denormalised onto the booking.
- `CO_TRAVELLER` — anyone else on the trip whom the agent has captured (other family members, friends in the party). Receives itinerary email by default; not addressed for payment.
- `PAYER` — the person settling the invoice. May be the same `Guest` as the LEAD (in which case no separate `BookingGuest(role=PAYER)` row is created — the LEAD also pays, by convention), or a different person who signs off and pays but does not travel (the PA-payer case). Receives payment-related comms.
- `CC_ONLY` — addressable for comms (booking summary, arrival reminder) but with no semantic role in the trip. Captures the legacy "CC the spouse / PA / family member" pattern; retained for marketing and continuity.

All four roles appear in marketing audiences by default — no role is silently excluded from outreach. Per-`Guest` `marketing_consent` is the opt-out signal, not the role.

#### Comms routing

The `comms.EmailService` dispatcher, when sending to "all guests on this booking", reads `BookingGuest` rows and addresses each one at `email_override or guest.email`. Per-role gating (e.g. payment reminders to PAYER only, itinerary to LEAD + CO_TRAVELLERs) is expressed in the email template's `to_roles` configuration rather than in the dispatcher. See `10-comms.md`.

#### `Booking.guest` FK during the transition `[OPEN]`

The existing `Booking.guest` FK and the new `BookingGuest(role=LEAD)` row encode the same fact. Two implementation options:

1. **Keep `Booking.guest`** as a denormalised pointer kept in sync with the LEAD row by signal — fast indexed reads on the booking list view, at the cost of a duplicated FK.
2. **Drop `Booking.guest`** in favour of a `booking.lead_guest` property that resolves through `BookingGuest` — clean but requires touching every read site.

Pick at implementation time. `10-decisions.md` records this as an open follow-up.

### `BookingHold`
Lives here logically but documented in 06-availability.md.

## Concierge

There is no separate `ConciergeService` catalogue model. Legacy `VillaConciergeServices` held exactly 2 tier-label rows ("Quintessential", "Signature"); a 2-row CRUD table doesn't earn its keep. The two tier labels collapse to a `ConciergeTier` TextChoices on `BookingConciergeItem`, and the per-item shape (name, description, unit price, unit, currency) moves directly onto the line item — which always varied per booking in practice. See reconciliation issue #34.

### `BookingConciergeItem(AuditedModel)`
- `booking` — FK CASCADE
- `tier` — TextChoices (`QUINTESSENTIAL`, `SIGNATURE`) — replaces legacy FK to `VillaConciergeServices`
- `name` — CharField (e.g. "Private chef — opening night", "Daily housekeeping")
- `description` — TextField(blank=True)
- `quantity` — PositiveSmallInteger
- `unit` — TextChoices (`DAY`, `STAY`, `EVENT`, `HOUR`)
- `unit_price` — Decimal(12, 2)  # snapshotted at add time; the row is the source of truth, no upstream catalogue to drift from
- `currency` — FK Currency PROTECT
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
- All transition methods on Booking (`submit`, `owner_approve`, `owner_decline`, `record_deposit`, `arm_balance`, `record_balance`, `check_in`, `check_out`, `cancel`, `expire`) wrap state mutation + event row + signal in `transaction.atomic`.
- Non-state-mutating audited mutations (`modify_dates`, `modify_guests`, `archive`, `restore`, `send_confirmation_email`) wrap their side effects + `BookingEvent` row in `transaction.atomic` but emit the event with `from_status == to_status` (the state machine doesn't advance). Date and guest modifications re-run the pricing engine and replace `pricing_snapshot`; see `06-availability.md` for the full method table.

## Signals

- `booking_transitioned(booking, from_status, to_status, actor, source)` — fired by every transition method.
- `payments.payment_succeeded` (from payments app) is **received** here; handler calls the matching booking transition (`record_deposit` or `record_balance` based on `payment.purpose`).

## Dropped from legacy

- `VillaArchiveBooking` — replaced by `Booking.is_archived=True` (operator hide-from-list flag) plus `BookingEvent` history. The terminal post-stay state itself is `Booking.status='CHECKED_OUT'`; archive is orthogonal to status.
- `VillaCheckoutDetail` — its fields scatter across `Booking`, `Guest`, and `Payment`. No separate entity; the checkout-page form posts to multiple endpoints.
- `IsActive`, `Tbc` booleans on Booking — collapsed into `status`.
- `IsOwnerConfirmed`, `IsDepositePaid`, `IsBankPaid` booleans — collapsed into `status`.
- `BookingUrl` — generated on demand via `reverse()`, not stored.
- Email link tracking / code sent history — out of scope here; lives in a future `comms` app if needed.
- `VillaBooking.Notes`, `VillaBooking.ConciergeNotes`, plus the unmapped Blazor "Internal booking information" / "Villa notes" textareas — collapsed into `BookingNote(kind, body, author)` rows. The legacy three-textarea page becomes three pre-filtered tabs over the same collection. Migration: one non-empty source column → one seed `BookingNote` row keyed by `kind`.
- `VillaEnquire.Notes`, `VillaEnquire.PreferencesNote` — the operator scratchpad fields collapse into `EnquiryNote(kind, body, author)`. The guest's original webform message is preserved as `Enquiry.inbound_message` (single immutable field, never edited) because it is provenance, not a note. Migration: one non-empty operator column → one seed `EnquiryNote` row keyed by `kind`.
