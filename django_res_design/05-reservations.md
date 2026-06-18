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

> ⚠️ **Being folded into `accounts.Person` (2026-06-18).** Per the
> `people-model-cleanup.md` banner + `10-decisions.md`, `Guest` merges with
> `accounts.Contact` into one `Person` identity; `BookingGuest` survives
> (repointed). Tracked by `todo/gap-045`. The fields/constraints below move onto
> `Person`.

Unified entity replacing the legacy `VillaEnquire` form fields + `VillaClientDetail`. Reused across enquiries, quotations, and bookings.

- `first_name`, `last_name` — CharField
- `title` — CharField(blank=True)
- `email` — `CIEmailField(db_index=True, null=True)` (case-insensitive via `citext`; **not** unique — same person legitimately books from different addresses; **optional** — a phone-only guest is valid, see contactability constraint below. No synthetic fabrication.) See `people-model-cleanup.md`.
- `phone` — CharField(blank=True) — stored **normalized E.164** (`phonenumbers`); the advisory dedup key
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

Constraints (see `people-model-cleanup.md`) — **scoped to `status=ACTIVE` rows
only** (`ARCHIVED`/`ANONYMIZED` are exempt; a channel-less historical row is
dispositioned, never forced to carry a channel):
- **Contactability** — `email IS NOT NULL` **OR** `phone <> ''` (email is now
  nullable; phone uses blank `''`, not NULL). Replaces the old fake
  email-required + synthetic-email fabrication.
- **Actionable preference** — `contact_method=EMAIL ⇒ email IS NOT NULL`;
  `contact_method IN (PHONE, SMS) ⇒ phone <> ''` (legacy `ContactType` parity).

Dedup is **advisory**: a resolve-or-create suggests a match on normalized
email → normalized phone; the operator confirms reuse or proceeds as new (no
silent auto-merge). `email` stays **non-unique** by design.

#### Lifecycle (per `00-conventions.md`)

- **Wrong guest captured, no relationships yet** — hard delete.
- **Guest no longer relevant but bookings exist** — set `status=ARCHIVED`. Still queryable; hidden from default operator search only by an explicit `?status=` filter at the call site, not a hidden manager.
- **`Guest.merge(target: Guest)`** — destructive. Atomically rewrites FKs on `Enquiry`, `Quotation`, `Booking` (and any `BookingConciergeItem` reached via `Booking`) from `self` to `target`. Writes one `AuditLog` row per rewrite. Then **hard-deletes** `self`. There is no `merged_into` self-FK and no surviving tombstone — the `AuditLog` is the only trail.
- **`Guest.anonymize()`** — overwrites `first_name`, `last_name`, `email` (set to `NULL` — `status=ANONYMIZED` marks the row, so no synthetic tombstone is needed; the contactability/preference constraints are ACTIVE-only, so an anonymized row needs no channel), `phone` (empty), `address_line_1`, `address_line_2`, `town`, `post_code`, `notes`; clears `marketing_consent`; sets `status=ANONYMIZED`, `anonymized_at=now()`. Bookings retain the FK pointing at the anonymized row. Reporting that should exclude anonymized guests filters `status` explicitly.

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
Anonymous / unstructured inquiry from website or agent. **Kept separate from Quotation** — different shape, different audit needs, different lifecycle. Bridge is `Quotation.enquiry`, now a **non-null `PROTECT` FK** (agent-direct quotes auto-create a minimal enquiry — see the `Quotation` field spec below and `10-decisions.md`); the earlier nullable-bridge was reversed.

- `reference` — CharField(unique=True) — short slug, e.g. `E-2026-000123`
- `guest` — FK Guest SET_NULL, null=True (set once captured; for purely anonymous form submits, hold the form fields below)
- `first_name`, `last_name`, `email`, `phone` — denormalised for anonymous submits (the raw inbound capture snapshot; **no** contactability constraint here — the enquiry is the permissive capture surface, `Guest` is the enforced-clean entity)
- `contact_method` — TextChoices (`EMAIL`, `PHONE`, `SMS`), null=True — captured preference that survives before a `Guest` exists; carried onto the `Guest` on resolve. See `people-model-cleanup.md`.
- `property` — FK properties.Property SET_NULL, null=True
- `region` — FK properties.Region SET_NULL, null=True
- `date_from` — DateField(null=True)
- `date_to` — DateField(null=True)
- `is_flexible` — BooleanField(default=False)
- `flexibility_days` — PositiveSmallIntegerField(default=0, `MaxValueValidator(3)`) — structured "± n days" flexibility around the requested dates. `date_from`/`date_to` hold the client's **true requested stay**; the quote-builder search widens its window by this value (`POST /quotations:search-options`). Added in the 2026-06 quote-builder rework — see "Date flexibility on intake" below for the override of the earlier dropped-encoding decision.
- `adults` — PositiveSmallInteger(default=2)
- `children` — PositiveSmallInteger(default=0)
- `min_bedrooms` — PositiveSmallInteger(null=True)
- `request_type` — TextChoices (`AVAILABILITY`, `INFO`, `QUOTE`, `BROCHURE`, `OTHER`)
- `referral_code` — CharField(blank=True)
- `agent` — FK accounts.Contact SET_NULL, null=True  # external agent / intermediary representing the guest; distinct from `assigned_to`
- `assigned_to` — FK User SET_NULL, null=True, blank=True, related_name="assigned_enquiries"  # internal staff owner of this enquiry, backing `?assigned_to=` filter and `:assign` action. Separate from `agent`: `agent` is who is *acting on behalf of the guest*; `assigned_to` is *which staff member owns the work*. See reconciliation issue #26.
- `site_source` — TextChoices (`MAIN_WEBSITE`, `AGENT_PORTAL`, `EMAIL_INBOUND`, `PHONE`, `OTHER`)
- `status` — TextChoices (`NEW`, `CONTACTED`, `QUOTED`, `LOST`, `CONVERTED`) — the **workflow stage**, advanced only by transition methods (below), never a free-choice edit
- `lead_status` — TextChoices (`HOT`, `WARM`, `COLD`, `DEAD`), default `WARM` — **lead temperature**, orthogonal to `status`. A subjective sales signal the operator sets directly (an inline dropdown that persists immediately), distinct from the workflow stage. Pushed to Zoho as a CRM tag (see `08-integrations.md`). New in the rebuild — legacy res2 had no lead-quality field; the res3 mockup introduced hot/cold/dead. See `10-decisions.md` "`Enquiry.lead_status`".
- `inbound_message` — TextField(blank=True) — the original message the lead submitted via the public form (single field, write-once at capture, treated as immutable provenance)

Indexes: `(status, created_at)`, `email`, `(property, date_from)`, `(lead_status, status)`.

Note collection is via `EnquiryNote` (see below). Operator scratchpads (legacy `Notes`, `PreferencesNote`, `internal_notes`) collapse into `EnquiryNote` rows with `kind` discriminator.

When a quotation is created from an enquiry, set `enquiry.status = QUOTED` and `quotation.enquiry = enquiry`. Conversion to a booking sets `enquiry.status = CONVERTED`.

#### Quote stack

One enquiry typically accumulates **multiple `Quotation` rows** over its lifetime — mid-single-digits is common, double-digits not unusual on long-cycle inquiries (per scoping-session 2026-05-26 with the site owner). The data shape already supports this via `Quotation.enquiry` FK; the conversion semantics are:

- **Conversion is measured per `Enquiry`, not per `Quotation`.** As soon as any child `Quotation.status` flips to `ACCEPTED`, the parent `Enquiry.status` transitions to `CONVERTED`. Reporting that quotes a "conversion rate" counts enquiries, not quotes. See decisions row "Conversion is measured per `Enquiry`, not per `Quotation`" in `10-decisions.md`.
- **Staff UI groups every quote under the parent enquiry.** Re-quoting is the default operator action on an open enquiry — a single ordered list (most recent first), with the most recent expanded by default. There is no separate top-level "quote-bundle" entity; the FK is enough.
- **Quote reference numbers increment globally.** `QVC123` (`Quotation.number` from a single global sequence), not within an enquiry. Grouping is via the FK, not a derived prefix. The *booking* number is carried forward from its accepted quote (`QVC123` → `VC123`); see GAP-006 and `01-domain-model.md` "Reference numbers".

#### Enquiry-list inline editing

The operator enquiry/quote list (the res3 "Quotes & Inquiries" table) exposes **inline
dropdowns that persist on change** for the two operator-owned, free-set fields: `assigned_to`
(salesperson — auto-set to whoever picks up the enquiry; a manager can re-assign) and
`lead_status` (temperature). Each inline edit PATCHes the single field and writes an
`EnquiryEvent` (`ASSIGNED` / `LEAD_STATUS_CHANGED`).

`status` (workflow stage) is **not** an inline free-choice dropdown — it advances only through
the transition methods below, driven by operator actions (contacting, sending a quote,
converting, losing). Surfacing stage as a free dropdown was a res3-mockup affordance the
stakeholder explicitly wanted replaced with action-driven transitions (`10-decisions.md`).

#### Date flexibility on intake *(updated 2026-06, quote-builder rework)*

Inquiry-takers routinely allow one to three days either side of the client's stated dates, because most guests are flexible around changeover days (typically Saturday, sometimes Sunday or Monday). The original design recorded this **destructively** — the intake form's "± n days" stepper shifted `date_from`/`date_to` themselves on submit and discarded the spread, losing the client's true dates. The user has **overridden** that: the spread is now the structured `Enquiry.flexibility_days` (0–3), `date_from`/`date_to` always hold the **true requested stay**, and the quote-builder search derives the window `requested ± flexibility_days` itself (offering changeover-to-changeover stay blocks inside it — see the `POST /quotations:search-options` notes in `04-pricing.md` and `06-availability.md`). `Enquiry.is_flexible=True` remains the client's *explicitly stated* flexibility — a display-only signal that never widens the search.

**Migration caveat:** enquiries captured before migration `reservations.0030` store already-widened dates (the destructive shift) with `flexibility_days=0`; the original requested dates are unrecoverable. The UI labels these widened dates "requested" — accepted, no special-casing.

The legacy `EnquireDateTypeString` field (`SpecificDays` / `ThreeDays` / `SevenDays` / `WholeDays`) encoded a flexibility preset at the column level and was dropped as carrying no operator-meaningful information after capture. `flexibility_days` partially reinstates structured capture for the "± a few days" case that turned out to matter operationally. See `workflows/07-enquiry/enquiry-intake.md` for the operator-side detail.

The single rule on these otherwise-free dates: when **both** are set, `date_to` must not precede `date_from` — enforced in `EnquiryWriteSerializer.validate` (a 400 keyed on `date_to`, mirrored client-side as a Zod refinement on the intake form). This is deliberately weaker than `Booking`/`QuotationLine`'s `CheckConstraint(date_from < date_to)`: there is **no DB constraint** (legacy rows may violate it, and a partial update that touches neither date is never re-judged), equal dates are allowed, and either date may still be set alone. Sending no date is `null`, not `""` — the intake form coerces an empty picker to `null` so it reads as "no date" rather than a malformed `DateField`.

**Flexibility wider than ± a few days *(known rough edge)*.** The 2026-06-08
demo surfaced cases the simple ±n-days spread does not represent well: a client
who can travel *any week in June*, or *one week within a named three-week
window*. The owner explicitly flagged this as an area with "problems around that
with the current system." `flexibility_days` (above) now covers the ±1–3-day
case structurally; for anything wider these still collapse to an open
`date_from`/`date_to` range plus `is_flexible=True` — the operator records the
widest plausible window and narrows by conversation. This is accepted for v1 but
**recognised as a rough edge**: structured multi-week flexible capture
should be revisited if multi-week availability search becomes a quoting
bottleneck. It is *not* introduced speculatively here.

**Owner direction (Loom 2026-06-17) — multi-week range quoting is now wanted.**
The owner's walkthrough of the Ben/owner mockup (https://vc-new-res-system.netlify.app/)
calls the fixed-date builder "not correct" and asks to quote a **date range** with
**per-week selection** (tick every week to quote). This is the "rough edge" above
graduating into a requirement, and it brings the date-range back that the rework
deliberately removed — so it is recorded as a **tension, not yet a hard reversal**:
the `flexibility_days` model (true requested dates, no destructive shift) still
holds, and whether multi-week range *replaces* the ±n-day stepper or *coexists*
with it is left open for the build. The mockup's Flex? values
(`Specific dates` / `+/- 3 days` / `+/- 7 days` / `Flexible`) also reinstate the
full legacy `EnquireDateTypeString` preset set (`SpecificDays` / `ThreeDays` /
`SevenDays` / `WholeDays`) — wider than today's 0–3 cap, so `flexibility_days`
needs widening plus an open "Flexible" mode. Tracked in
[`todo/gap-043-quote-builder-multi-week-range.md`](todo/gap-043-quote-builder-multi-week-range.md)
(builder) and [`todo/gap-039-enquiry-dashboard-enrichment.md`](todo/gap-039-enquiry-dashboard-enrichment.md)
(the Flex? column).

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
- `kind` — TextChoices (`STATUS_CHANGE`, `ASSIGNED`, `UNASSIGNED`, `CONTACTED`, `QUOTE_SENT`, `CONVERTED`, `LOST`, `REOPENED`, `NOTE_ADDED`, `LEAD_STATUS_CHANGED`) — keeps the activity stream queryable without parsing free-text reasons. `LEAD_STATUS_CHANGED` is non-transitional (`from_status == to_status`); the temperature change rides in `meta` (`{"lead_status_from": "WARM", "lead_status_to": "HOT"}`)
- `actor` — FK User SET_NULL, null=True
- `source` — TextChoices (`USER`, `OWNER`, `WEBHOOK`, `SYSTEM`, `ADMIN`)
- `reason` — CharField(blank=True)
- `meta` — JSONField(default=dict)  # e.g. `{"assignee_from": 12, "assignee_to": 34}` for assignment changes; `{"quotation_id": 99, "send_path": "smtp" | "manual"}` for `QUOTE_SENT` — `send_path` is required on every `QUOTE_SENT` event (enforced by `Enquiry.quote_sent`'s keyword-only signature) so reporting can distinguish in-app SMTP sends from copy-paste-to-Outlook manual confirmations

Indexes: `(enquiry, created_at)`.

Enquiry history is `events.order_by('created_at')` — same pattern as `BookingEvent`. Every transition method on `Enquiry` (`contact()`, `quote_sent()`, `assign(user)`, `convert()`, `lose(reason)`, `reopen()`) writes one row in the same `transaction.atomic` block. `set_lead_status(value)` is a non-transitional mutation (it leaves `status` unchanged) that writes a `LEAD_STATUS_CHANGED` event for the activity timeline. `NOTE_ADDED` is the only event-kind written outside a transition method — emitted by an `EnquiryNote.post_save` signal so the activity timeline shows note authorship inline with status changes.

See reconciliation issue #27.

## Quotation

### `Quotation(AuditedModel)`
- `number` — PositiveIntegerField(null=True, unique=True) — canonical sequence-backed integer (`quotation_number_seq`); NULL only on synthesised/interim rows
- `reference` — CharField(unique) — `QVC123` (legacy parity), derived from `number` via `core.refs.quotation_prefix()`
- `enquiry` — FK Enquiry PROTECT, **null=False** — every quotation has a parent enquiry. Agent-direct quotes **auto-create a minimal enquiry** in the quote-creation service (legacy `sp_quotationMaster` parity), tagged via `site_source`, rather than carrying a null bridge. See `people-model-cleanup.md` (migration backfills existing null rows first).
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

- `reference` — CharField(unique) — `VC123` (legacy parity), **carried forward** from the source quotation's `number` (`QVC123` → `VC123`); falls to a `VC-TMP-…` sentinel when the quotation has no `number`. See `core.refs.booking_prefix()` and GAP-006.
- `quotation_line` — FK QuotationLine PROTECT  # real FK, not the legacy integer `QuotationNo`
- `guest` — FK Guest PROTECT
- `property` — FK properties.Property PROTECT  # denormalised from quotation_line for query speed; enforced equal in clean()
- `date_from`, `date_to` — DateField
- `adults`, `children` — PositiveSmallInteger
- `currency` — FK pricing.Currency PROTECT
- `pricing_snapshot` — JSONField  # **copied from QuotationLine at creation, never recomputed**
- `rental_price` — Decimal(12, 2)  # extracted for reports
- `discount` — Decimal(12, 2, default=0)
- `adjustment` — Decimal(12, 2, default=0)  # concierge total **only** (signal-maintained from `BookingConciergeItem`; settles on its own CONCIERGE payment track, never enters `total`). Manual money lines live on `BookingChargeItem`, not here.
- `balance_due` — Decimal(12, 2)  # computed at creation. Despite the name this is the **denormalised engine-gross total** (snapshot `total`), never decremented as payments settle — outstanding is computed from Payment rows (07-payments.md). The API `total` is `balance_due` **plus the live Σ of `BookingChargeItem` rows** (no denormalised charges column — computed via a Subquery annotation / per-row aggregate), so a re-price rewriting `balance_due` never wipes manual charges. The legacy loader fills it from `RentalPrice` (legacy `BalanceDue` is a DATETIME — the due *date* — not money).
- `balance_due_at` — DateField  # derived from PaymentSchedule; the legacy loader maps `VillaBooking.BalanceDue` (datetime) here
- `status` — TextChoices (see 06-availability.md for full machine)
- `agent` — FK accounts.Contact SET_NULL, null=True  # external agent / intermediary; same distinction as Enquiry.agent
- `assigned_to` — FK User SET_NULL, null=True, blank=True, related_name="assigned_bookings"  # internal staff owner of this booking, backing `?assigned_to=` filter and `:assign` action. See reconciliation issue #26.
- `site_source` — TextChoices (mirror Enquiry.site_source)
- `terms_version` — FK TermsVersion PROTECT
- `terms_accepted_at` — DateTimeField
- `payment_method` — TextChoices (`CARD`, `BANK_TRANSFER`)
- `checkout_url` — URLField(blank=True)  # first-party SPA guest-checkout link (`portal.villacollective.com/booking?ref=<reference>`). Replaces the legacy WordPress `VillaBooking.BookingUrl`: the checkout journey is hosted in the SPA, not WordPress, so this is an internally-generated route, not a value pushed back from WP. See `10-decisions.md` "Guest booking/checkout journey hosted in the SPA" and `workflows/10-payment/checkout-flow.md`.
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

#### `Booking.guest` denorm + LEAD invariant

`Booking.guest` is kept as a denormalised pointer to the LEAD guest, kept in sync from `BookingGuest` by signal:

- `_booking_guest_post_save` mirrors the LEAD row onto `Booking.guest` via queryset `.update()` (skips `Booking.save()` so the audit trail stays on `BookingGuest` and `Booking.updated_at` is not bumped by denorm churn).
- `_booking_guest_pre_delete` raises `LeadGuestProtectedError(ProtectedError)` if a LEAD row is deleted while its booking still exists. Cascade-safe via Django's `origin` kwarg — `Booking.delete()` cascades through `BookingGuest` cleanly without firing the guard.
- Recommended swap pattern (when the LEAD guest changes mid-booking): demote the old LEAD to `CO_TRAVELLER` and create the new LEAD row, both inside one `transaction.atomic`. Deleting the old LEAD first will raise.

`BookingService.create_from_quotation_line` creates the `BookingGuest(role=LEAD)` row inside the same `transaction.atomic` as the `Booking` — so the invariant is established at booking creation, not papered on by a signal. `data_migration.loaders.bookings.BookingLoader` does the same via idempotent `get_or_create`, so re-runs don't double up.

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

## Manual charge items

Legacy `VillaBookingDetails` rows (Price + Notes + CurrencyId) were staff-entered
money lines on a booking — negotiated extras, mid-stay charges, one-off
corrections — and legacy regenerated the payment schedule on every save. The
rebuild's analogue (supersedes the earlier "extras collapse into `adjustment`"
plan — `adjustment` is concierge-only):

### `BookingChargeItem(AuditedModel)`
- `booking` — FK CASCADE, related_name `charge_items`
- `label` — CharField(200)  # legacy `Notes` was the display label
- `amount` — Decimal(12, 2) **signed** — negative = credit. CheckConstraint `amount != 0`.
- `currency` — FK pricing.Currency PROTECT  # service-validated equal to `booking.currency`; kept per-row for legacy-import parity
- `notes` — TextField(blank=True)
- `legacy_id` — nullable, indexed

Semantics:

- **Guest total:** API `total = balance_due + Σ charge_items`, computed live
  (Subquery annotation; no denormalised column). The snapshot is never touched.
- **Payment schedule:** every mutation fires `booking_total_changed`;
  payments' receiver runs `PaymentScheduler.resync_for_booking`, which resizes
  **PENDING** deposit/balance rows only (SUCCEEDED is history, PROCESSING is
  mid-flight at the provider). Unabsorbable residuals clamp PENDING at 0 and
  are logged + written to a `BookingEvent` (`payment_schedule_residual`).
- **Owner accounting (legacy-style):** charges enter the commissionable base.
  PERCENT commission skims its share off every charge (credits shared
  symmetrically); FIXED commission passes charges to the owner in full.
  Computed read-side by `reservations.services.charges.owner_effect` and
  layered onto the serializer's `net_to_owner`; tax never recomputed (charges
  are entered gross). The owner portal applies the same effect via
  `owner_finance.owner_money_for_booking` (booking detail + dashboard YTD
  net), so staff and owner surfaces always agree. Percent security deposits
  size against the charges-inclusive total at creation (see GAP-019 for the
  no-resync caveat).
- **State gate:** writes allowed in exactly `ACTIVE_BOOKING_STATUSES`
  (including CHECKED_IN — mid-stay charges are a core use case); DRAFT /
  PENDING_OWNER_APPROVAL / terminal → 409.
- **Service layer:** `ChargeItemService` (create/update/delete, `actor` kwarg)
  owns the booking row lock, the state gate, the currency pin, the
  negative-combined-total guard and the `BookingEvent` audit trail (reason
  `charge_item_{created,updated,deleted}` with before/after meta).
- **API:** nested CRUD `/bookings/{id}/charge-items` (+ `/{pk}`), writes
  respond with the read representation.

## Terms

### `TermsVersion(TimestampedModel)`
Append-only legal copy versions.
- `version` — CharField(unique)  # e.g. "2026-01"
- `published_at` — DateTimeField
- `body_markdown` — TextField
- `is_current` — bool(unique constraint with condition `is_current=True`)

Both `Quotation.terms_version` and `Booking.terms_version` snapshot the version active at creation.

## Services

- `QuotationService.create_from_enquiry(enquiry, lines: list[dict]) -> Quotation` — builds Quotation + QuotationLines, runs PricingEngine per line, snapshots. Places **no** holds — quoting never blocks availability.
- `QuotationService.hold_line(line, *, actor=None) -> BookingHold` / `release_line_hold(line, *, actor=None)` / `move_line_hold(line)` — the manual per-line hold lifecycle (operator-driven via `lines/{id}:hold` / `:release-hold`); expiry from the property's effective `hold_duration_hours`. See 06.
- `BookingService.create_from_quotation_line(quotation_line, terms_version, payment_method, ...) -> Booking` — copies `pricing_snapshot`, computes `balance_due` and `balance_due_at` via effective PaymentSchedule, sets initial status `PENDING_OWNER_APPROVAL` or `AWAITING_DEPOSIT` per property config, releases competing holds, writes `BookingEvent`.
- `HoldService` — see 06.
- All transition methods on Booking (`submit`, `owner_approve`, `owner_decline`, `record_deposit`, `arm_balance`, `record_balance`, `check_in`, `check_out`, `cancel`, `expire`) wrap state mutation + event row + signal in `transaction.atomic`.
- Non-state-mutating audited mutations (`modify_dates`, `modify_guests`, `archive`, `restore`, `send_confirmation_email`) wrap their side effects + `BookingEvent` row in `transaction.atomic` but emit the event with `from_status == to_status` (the state machine doesn't advance). Date and guest modifications re-run the pricing engine and replace `pricing_snapshot`; see `06-availability.md` for the full method table.

## Signals

- `booking_transitioned(booking, from_status, to_status, actor, source)` — fired by every transition method.
- `booking_total_changed(booking)` — fired from `BookingChargeItem` post_save/post_delete (so direct ORM writes trigger it too). payments listens and resizes the unsettled DEPOSIT/BALANCE schedule (`PaymentScheduler.resync_for_booking`) — the signal exists because the spine forbids `reservations -> payments`.
- Reservations registers **no** receiver on payments' signals — the import spine forbids `reservations -> payments`. The booking-advance dispatch (`payment_succeeded`/`payment_waived` -> `record_deposit`/`record_balance` by `payment.purpose`) is owned by the payments app (`payments/signals.py`, `_advance_booking_on_payment_settled`), a clean downward edge mirroring `_schedule_payments_on_booking_confirmed`.
- Reservations' own beat tasks (`reservations/tasks.py`) drive the time-based transitions: `expire_quotations` (DRAFT/SENT past `expires_at`), `expire_bookings` (AWAITING_DEPOSIT whose deposit Payment `due_at` is older than `BOOKING_DEPOSIT_EXPIRY_DAYS`; the booking's leftover PENDING payments are expired by a payments-side `booking_transitioned` receiver), and `arm_balances` (DEPOSIT_PAID on/after `balance_due_at`).

## Dropped from legacy

- `VillaArchiveBooking` — replaced by `Booking.is_archived=True` (operator hide-from-list flag) plus `BookingEvent` history. The terminal post-stay state itself is `Booking.status='CHECKED_OUT'`; archive is orthogonal to status.
- `VillaCheckoutDetail` — its fields scatter across `Booking`, `Guest`, and `Payment`. No separate entity; the checkout-page form posts to multiple endpoints.
- `IsActive`, `Tbc` booleans on Booking — collapsed into `status`.
- `IsOwnerConfirmed`, `IsDepositePaid`, `IsBankPaid` booleans — collapsed into `status`.
- `BookingUrl` — generated on demand via `reverse()`, not stored.
- Email link tracking / code sent history — out of scope here; lives in a future `comms` app if needed.
- `VillaBooking.Notes`, `VillaBooking.ConciergeNotes`, plus the unmapped Blazor "Internal booking information" / "Villa notes" textareas — collapsed into `BookingNote(kind, body, author)` rows. The legacy three-textarea page becomes three pre-filtered tabs over the same collection. Migration: one non-empty source column → one seed `BookingNote` row keyed by `kind`.
- `VillaEnquire.Notes`, `VillaEnquire.PreferencesNote` — the operator scratchpad fields collapse into `EnquiryNote(kind, body, author)`. The guest's original webform message is preserved as `Enquiry.inbound_message` (single immutable field, never edited) because it is provenance, not a note. Migration: one non-empty operator column → one seed `EnquiryNote` row keyed by `kind`.
