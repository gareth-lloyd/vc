# GAP-020 — Direct booking creation (legacy rate-lookup "book now", done properly)

- **Severity:** 🟢 Gap / feature — **design ready; implementation deliberately
  deferred** (decision locked 2026-06-10).
- **Source:** property-detail quick actions shipped disabled ("Create booking"
  tooltip "Coming in next phase"); legacy investigation of
  `ResSystem/NewResSystem/Pages/Bookings/RateLookup/RateLookup.razor` +
  `Booking.razor`; `product-design/03-workflows.md` flow 4;
  `workflows/09-booking/booking-creation.md`; GAP-006's open sub-question.
- **Files (future implementation):**
  - `reservations/services/bookings.py` (`BookingService.create_direct`)
  - `reservations/models/quotation.py` (`kind` field, `real()` semantics)
  - `reservations/models/enquiry.py` (`kind` field)
  - `reservations/models/booking.py` (`meta` field for idempotency)
  - `reservations/views/booking.py` (`POST /bookings`), new price-check view
  - `frontend/src/features/bookings/` (`/bookings/new` page),
    `frontend/src/features/properties/PropertyDetailLayout.tsx` (quick action)

## Problem

The rebuild has no way to create a booking except by converting a quotation
(`POST /quotations/{id}:convert`). The property-detail "Create booking" quick
action is a disabled placeholder, and flow 4 of `product-design/03-workflows.md`
(Direct Booking Creation) is unimplemented with two stated difficulties
unresolved:

1. **Reference numbering.** `Booking.reference` carries the legacy
   `VC{quotation.number}` carry-forward (GAP-006); a booking with no
   quotation has no number to carry and falls to the `VC-TMP-…` sentinel.
   GAP-006 explicitly deferred this sub-question.
2. **The FK chain assumes a quote.** `Booking.quotation_line` and
   `Quotation.enquiry` are non-null PROTECT FKs. Flow 4's departure note (a)
   promised "no shadow enquiry+quote records — tag `origin=direct`", which
   would mean relaxing both FKs *and* the reference scheme. That departure
   was written before the carry-forward decision and is now the expensive
   path.

## Legacy intention (verified against source)

Legacy has **no standalone direct-booking form**. The verified mechanics:

- The booking page routes are `/booking/{QuotationNo:int}/{Id:int}` plus a
  degenerate bare `/booking` (`Booking.razor:1-2`). The villa on the form is
  a **read-only card** — no picker; the villa can only arrive via a
  quotation. The bare route renders an empty model titled plain
  "Booking Ref" (no number).
- The real "book now" path is **Rate Lookup** (`RateLookup.razor:894`,
  `StartBooking`): staff search villa/dates/price, click book; the code
  first persists quotation-detail rows (`SaveQuotationDetails`), then
  INSERTs the booking with the `QuotationNo` attached, then navigates to
  `/booking/{QuotationNo}/{id}`. **Even the shortcut mints quote records** —
  and the booking's customer-facing reference is `VC{QuotationNo}`.
- The save path proper is documented in
  `workflows/09-booking/booking-creation.md`
  (`BOOKING.LIFECYCLE.CREATE_FROM_QUOTATION`) — the **verified** legacy
  locus, including the full input set (payer details, deposit % override,
  security-deposit override, concierge, 3-tier payment schedule,
  full-payment short-circuit).

So the *intention* behind legacy rate-lookup booking is: **one screen where
an operator answers a phone enquiry end-to-end — find the villa, see the
price, take the booking — without ceremonial enquiry/quote steps.** The
quote records it wrote were plumbing, not workflow.

> Caveat: `product-design/03-workflows.md` flows 3–4 belong to the tree that
> GAP-010 flagged as partly inferred from a post-deletion checkout. The
> mechanics above were re-verified directly against `RateLookup.razor` /
> `Booking.razor` (2026-06-10) and against `workflows/09-booking/`, which is
> legacy-derived. Treat *this* doc as the canonical direct-booking spec.

## Decision (locked with the user, 2026-06-10)

**Synthetic quotation.** A direct booking synthesises its own
Enquiry → Quotation → QuotationLine chain — the same shape
`data_migration.loaders.bookings.BookingLoader` already uses to satisfy the
PROTECT FK chain for imported bookings — and the synthetic rows are
structurally hidden from operator/guest reads.

The key insight that makes this clean: unlike migration synthetics (which
must leave `Quotation.number` NULL because the real `QVC{n}` quotation owns
that number), an organic direct booking has **no competing quote** — its
synthetic quotation draws the next value from `quotation_number_seq` through
the existing `Quotation.save()` hook, and the booking's reference falls out
as `VC{n}` with **zero special-casing** in reference logic.

This:

- **resolves GAP-006's open sub-question** — direct bookings are `VC{n}`
  via their synthetic quotation's organically-allocated number; the
  `VC-TMP-…` sentinel remains *only* for migrated bookings whose synthetic
  quote has no number;
- **is true legacy parity** — legacy's book-now path also wrote quotation
  rows carrying the number (see above), so the reference series behaves
  identically across cutover;
- **supersedes flow 4's departure note (a)** ("no shadow records"). We *do*
  create the rows; the improvement over legacy is that they are explicitly
  marked and structurally invisible, and attribution comes from
  `AuditedModel.created_by` + `Booking.site_source` rather than archaeology.

A hidden `QVC{n}` reference now exists for a quote no guest ever received.
That is deliberate and harmless (legacy's book-now quotes were equally
unsent); do not "reclaim" such numbers.

## Proposed design

### 1. Synthetic-row marking — `kind` enum, not `legacy_id` (folds SMELL-014)

`legacy_id` is migration metadata only (`django_res/CLAUDE.md`) and must not
be minted for organic rows. Instead:

- Add `kind` (TextChoices: `OPERATOR` default / `LEGACY_BACKFILL` /
  `DIRECT_BOOKING`) to **Enquiry** and **Quotation** (QuotationLine derives
  via its parent; add the column there only if a query needs it directly).
- `QuotationQuerySet.real()` / line equivalent become
  `exclude(kind != OPERATOR)` — a structural predicate instead of the
  string-prefix convention SMELL-014 criticises. A data migration stamps
  existing `legacy_id__startswith="booking-"` rows as `LEGACY_BACKFILL`.
- **Enquiry pipeline views must filter too.** Today the migrated synthetic
  enquiries are *not* excluded from `EnquiryViewSet` (latent leak, observed
  2026-06-10 — fold into this work). Direct-booking enquiries must not
  pollute the funnel: pipeline/list views exclude non-`OPERATOR` kinds; the
  synthetic enquiry stays reachable from its booking detail.
- Funnel/conversion reporting must count `kind=OPERATOR` only.

### 2. Synthetic rows are inert carriers — state-machine exemption, stated

The service creates the rows directly in their terminal-truthful states —
Enquiry `BOOKED`, Quotation `ACCEPTED`, line `is_selected=True` — *without*
running `send()`/`accept()`. This bypass is safe because:

- the quotation expiry beat targets `DRAFT`/`SENT` only — an
  `ACCEPTED`-from-birth quote is never touched;
- `accept()`'s side effects (enquiry conversion, hold release) are
  irrelevant: the enquiry is born `BOOKED` and no holds exist;
- the audit trail lives on the **booking** (BookingEvent + AuditLog +
  `booking.created` log event), which is the entity the operator actually
  created. Synthetic rows deliberately have no event history.

An `ACCEPTED` quotation that was never `SENT` is a state combination unique
to `kind != OPERATOR` rows; any future lifecycle logic keyed on quotation
status must filter on `kind` first (add this to the `.real()` docstring).

### 3. Service — `BookingService.create_direct`

```python
BookingService.create_direct(
    *, property, date_from, date_to, adults, children,
    guest,                      # existing Guest (FE handles search-or-create first)
    currency=None,              # None → rate plan's currency (GAP-014 semantics)
    manual_price=None,          # required iff engine raises NoRateAvailable
    price_override_reason=None, # required with manual_price
    agent=None, payment_method=PaymentMethod.CARD,
    actor, idempotency_key=None,
) -> Booking
```

One `transaction.atomic()` block:

1. **Idempotency short-circuit.** There is no natural key (each call would
   synthesise a fresh line), so use the `meta`-key convention
   (`core/idempotency.py`): add `meta = JSONField(default=dict, blank=True)`
   to `Booking` (today only `BookingEvent` has one), scope
   `find_by_meta_key(Booking.objects.filter(property=…, date_from=…,
   date_to=…), key)`, return the existing booking on a hit, `stamp_meta` on
   create. Operator double-click → original booking back, no duplicate
   enquiry/quote/number.
2. **Availability check** via `AvailabilityService.is_available` (bookings
   via `Booking.objects.occupying`, holds via
   `BookingHold.live_overlapping`). On conflict raise the structured
   conflict error (§5).
3. **Price** via `PricingEngine.quote(allow_projection=False)` (strict — no
   guide rates on a money path). On `NoRateAvailable`: require
   `manual_price` + `price_override_reason`, mark the line
   `is_manual=True` — Q-013's resolved flag-and-manual-quote behaviour
   (villa never blocked; legacy "NO RATE" rows stayed bookable). Manual
   price requires an explicit `currency` (no plan to infer one from).
4. **Synthesise** Enquiry (`kind=DIRECT_BOOKING`, status `BOOKED`,
   guest/agent set, source per §7) → Quotation (`kind=DIRECT_BOOKING`,
   status `ACCEPTED`, `number` allocated by the existing save hook, current
   `terms_version`) → QuotationLine (`is_selected=True`, engine
   `pricing_snapshot` or manual price).
5. **Delegate to `create_from_quotation_line`** unchanged — LEAD
   `BookingGuest` invariant, terms snap, pre-approval vs auto-accept branch,
   `booking_transitioned` signal → `PaymentScheduler`, structured
   `booking.created` event all come for free. Booking reference derives as
   `VC{number}` through the existing path.

**Race backstop:** `OVERLAP_BLOCKING_BOOKING_STATUSES` includes
`PENDING_OWNER_APPROVAL` (verified, `reservations/enums.py:101`), and the
initial transition happens inside the same transaction — so two concurrent
creates for overlapping dates cannot both commit; the loser's
`booking_no_overlap_blocking` IntegrityError rolls back its synthetic rows
too. The burnt sequence number is acceptable (sequences are
non-transactional; uniqueness matters, density doesn't — legacy numbering
had gaps).

### 4. API surface

- **`POST /bookings`** — `BookingViewSet` already mixes `CreateModelMixin`;
  give it a `BookingCreateSerializer` that feeds `create_direct`. Role
  gating per the existing reservations-writer pattern; service re-checks via
  `actor_has_perm`.
- **`GET /properties/{id}/price-check?from=&to=&adults=&children=[&currency=]`**
  — thin read-only wrapper over `AvailabilityService` +
  `PricingEngine.quote(allow_projection=False)` returning
  `{available, conflicts: […], price: {…breakdown…} | null, no_rate: bool}`.
  Powers the live availability+price strip (debounced). Deliberately *not*
  the multi-villa quote-options search — that is a heavyweight POST for the
  quote builder; this is a single-villa, cacheable read.

### 5. Conflict error shape (flow 3/4's "conflict panel")

One shape for both the pre-check failure and the EXCLUDE-constraint
IntegrityError (map the latter, don't leak a 500 — cf. SMELL-010):

```json
409 {"detail": "...", "code": "booking_conflict",
     "conflict": {"type": "booking|hold", "id": …, "reference": "VC…",
                  "date_from": …, "date_to": …, "status": "…"}}
```

Operator-only endpoint, so exposing the conflicting reference is fine —
that's the panel's whole point ("Conflict with VC1234 — open it / adjust
dates").

### 6. Form scope — v1 cut, explicitly

Flow 4 says "identical to flow 3 from Money onward", but the rebuild's
*actual* conversion surface is minimal (line + payment_method), and the
booking detail page already owns post-create adjustment (charge items
GAP-018, price override GAP-016, `:modify-dates` / `:modify-guests`,
payments tab). v1 direct-booking form therefore captures **only**: villa,
dates, party, guest (search-or-create, flow-1 duplicate detection),
currency, manual price + reason when NO RATE, agent toggle, payment method,
internal note. **Deliberately deferred to the booking detail page or later
phases:** payer-different-from-guest, deposit %/amount override,
balance-due-date override, security-deposit override, concierge tier.
(Legacy's create form did carry all of these —
`workflows/09-booking/booking-creation.md` Inputs — but in the rebuild they
are post-create concerns; do not silently re-grow the form.)

**Deposit-request CTA reconciliation:** in the rebuild, payment *scheduling*
is signal-driven and unconditional (`booking_transitioned` →
`PaymentScheduler` on `AWAITING_DEPOSIT`). Flow 3/4's "Create booking
without deposit request" choice therefore controls **comms only** (suppress
the deposit-request email, reason captured) — it does not and must not skip
the schedule. The v1 form can ship with the single "Create booking" CTA and
add the email-suppression option when the comms flow lands.

### 7. Attribution

No `origin` field: `AuditedModel.created_by` records the operator,
`quotation.kind=DIRECT_BOOKING` is the machine-readable origin, and
`Booking.site_source` records the channel. Confirm at implementation whether
`EnquirySource` needs a staff-direct value (e.g. `PHONE`/`STAFF`) or an
existing value fits.

### 8. Frontend

- `/bookings/new` full-page form (flow 4 entry points: global "+", Cmd-K,
  **property quick action** `Create booking` →
  `/bookings/new?property=:id[&from=&to=]` — finally enabling one of the
  three disabled `QuickActions` on `PropertyDetailLayout.tsx`; calendar-cell
  entry waits for the §3.5 timeline).
- Live strip from the price-check endpoint; NO-RATE state swaps the price
  display for the manual-price + reason inputs (Q-013).
- 409 `booking_conflict` renders the conflict panel (link to conflicting
  entity, "adjust dates"); 4xx field errors via `applyApiErrorToForm` as
  usual.

## Difficulties overcome (the checklist)

| Stated difficulty | Resolution |
|---|---|
| Direct bookings have no quotation number to carry forward (GAP-006 open sub-question) | Synthetic quotation draws a real `quotation_number_seq` value → booking is `VC{n}` through the unchanged derivation path |
| `quotation_line` / `enquiry` non-null PROTECT FKs | Satisfied by the synthetic chain; no FK relaxation, `create_from_quotation_line` reused verbatim |
| "Shadow records" pollute operator lists (flow 4's original objection) | `kind` enum + structural `.real()` (SMELL-014's fix); enquiry pipeline filtered too |
| Operator double-click / webhook-style retries duplicate the whole chain | `idempotency_key` via `Booking.meta` + `find_by_meta_key`, scoped to property+dates |
| Double-booking race | Pre-check via `AvailabilityService` + `booking_no_overlap_blocking` EXCLUDE backstop (`PENDING_OWNER_APPROVAL` is blocking); IntegrityError mapped to the same 409 shape |
| Incomplete rate card | Q-013 resolved behaviour: flag + manual price + mandatory reason, `is_manual` line; never hides the villa |
| Legacy had no villa picker / degenerate bare `/booking` | Full-page form with search-as-you-type picker + live price-check strip (the actual improvement over legacy) |

## Acceptance (when implemented)

- `POST /bookings` creates a booking referenced `VC{n}` where `n` came from
  `quotation_number_seq`; no `VC-TMP-…` for organic direct bookings.
- The synthetic enquiry/quotation/line never appear in any list endpoint
  (enquiries, quotations, quote search) — pinned by tests on `kind`
  filtering, including the enquiry pipeline.
- Double-submit with the same `idempotency_key` returns the same booking;
  concurrent overlapping creates → exactly one booking + one 409 with
  `code=booking_conflict`.
- NO-RATE villa bookable with `manual_price` + reason; without reason → 400
  field error.
- Pre-approval property → booking lands `PENDING_OWNER_APPROVAL`; otherwise
  `AWAITING_DEPOSIT` with the payment schedule created by the existing
  signal path.
- LEAD `BookingGuest` row exists; AuditLog rows carry the operator.

## Doc reconciliation (do alongside implementation)

- `product-design/03-workflows.md` flow 4 — rewrite departure (a) and the
  "skeleton enquiry is not created" line to match this decision; point here.
- `gap-006-legacy-reference-format-parity.md` — close the "Open
  sub-question (deferred)"; update Decision bullet 5.
- `10-decisions.md` — decision row (2026-06-10, synthetic-quotation
  numbering for direct bookings; supersedes flow-4 departure (a)).
- `smell-014` — note the second synthetic-row producer and that the `kind`
  enum is the agreed structural fix.
- `django_res/CLAUDE.md` "Synthesised rows" convention — update from
  `legacy_id` prefix to `kind` once implemented.

## Open questions

- **`terms_accepted_at` for staff-created bookings** — stamping "now" means
  "operator affirms the guest accepted T&Cs", which is what
  `create_from_quotation_line` already does; SMELL-006 owns the field's
  wider semantics. Confirm before launch whether phone bookings need an
  explicit affirmation checkbox.
- **`EnquirySource` value** for staff-direct (see §7).
- **Visibility of migrated synthetic enquiries** — the existing
  `LEGACY_BACKFILL` enquiries are visible in the pipeline today; decide
  whether stamping+filtering them is a behaviour change anyone will notice
  (they may be load-bearing for historical lists).

## Dependencies

- **GAP-006** (resolved) — number sequence + carry-forward this design rides on.
- **SMELL-014** — the `kind` enum is its fix; land together.
- **Q-013** (resolved) — manual-price behaviour.
- **GAP-014** (resolved) — currency semantics for the engine call.
- **GAP-016 / GAP-018** — post-create price adjustment surfaces that justify
  the v1 form cut.
- **BUG-004** (resolved) — the overlap-blocking `PENDING_OWNER_APPROVAL`
  guarantee §3 relies on.
