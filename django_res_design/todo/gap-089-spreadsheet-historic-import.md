# GAP-089 — Historic import pivot: bookings from spreadsheets, enquiry top-up

- **Severity:** 🟢 Gap (cutover-path change). **⛔ BLOCKED on Nick's sample
  sheets** (column structure) — design past the skeleton below waits for
  them.
- **Source:** Limitless call 2026-07-29 — **import pivot decision**:
  historic bookings will come from Nick's spreadsheets ONLY; the legacy
  res-DB booking data (~60 thin archive rows) is **ignored** for import.
  Enquiries stay on the res-DB migration path; spreadsheets only top up
  enquiries that are not in res. Filed 2026-07-29.
- **Files:**
  - `django_res/data_migration/loaders/bookings.py` — the legacy
    `BookingLoader`: **dead for cutover** (code stays as schema record).
    Reuse its `created_at` back-stamp technique (~L189-197: queryset
    `.update()` bypasses `auto_now_add`, fires no signals).
  - `django_res/reservations/models/quotation.py` —
    `SYNTHETIC_LEGACY_PREFIX = "booking-"` (~L23): the synthetic-quotation
    namespace `.real()` excludes and the Zoho booking payload flags as
    `quote.is_synthetic`
    (`reservations/services/zoho_payload.py` ~L344).
  - `django_res/data_migration/CUTOVER.md` — §4 blockquote updated
    2026-07-29: the FULL-legacy-booking-load-before-backfill step is
    superseded by this ticket.

## Problem

The res legacy DB holds only ~60 thin archive booking rows — Nick's
spreadsheets are the real historic record (and carry data res never had,
e.g. tags). The call pivoted the cutover plan accordingly:

- **Bookings:** spreadsheet import only. This supersedes the GAP-082
  requirement to run a FULL legacy booking load before
  `zoho_backfill --kinds booking`.
- **Enquiries:** res-DB migration stays primary; spreadsheets top up
  enquiries absent from res.
- **Zoho constraint:** Zoho filters historic imports out of its views on
  `booking_date` — which our payload maps from `Booking.created_at` — so
  spreadsheet-imported bookings MUST back-stamp `created_at` from the
  sheet's booking date.

Known sheet shapes (from the call; samples pending): inquiries sheet =
first name, last name, email, phone, villa, country, notes; bookings sheet
is more complex and carries **tags**.

## Proposed fix

Two importers (management commands in `data_migration/`, same idempotency
conventions as the loaders — upsert on a stable per-row key, e.g.
`sheet-booking-{n}` / a source-row hash; suppression of payment resync and
Zoho auto-push during load, as GAP-017/GAP-081 established):

1. **Booking sheet importer**
   - Mint a synthetic `Quotation` + `QuotationLine` per booking with the
     `booking-` legacy prefix, so the row is excluded from `.real()` and
     `quote.is_synthetic` flows to Zoho — exactly the legacy
     `BookingLoader` pattern.
   - **Back-stamp `Booking.created_at`** from the sheet's booking date via
     the queryset-`.update()` technique (Zoho's historic filter).
   - **Person match/dedupe by email** against the migrated contacts
     (`client-{Id}` Person rows) — match → link, no match → create.
   - **Villa match by name** against migrated properties; unresolvable
     names land in an errors report, not a guess.
   - **Carry tags** — open decision on the destination: `Booking` has no
     tags field, and `Person.tags` is the fixed GAP-040 `PersonTag` enum.
     Decide once the sample sheet shows what the tags actually are
     (per-person → map/extend `PersonTag`; per-booking → new column or
     notes).
2. **Enquiry top-up importer**
   - Import **only** enquiries absent from res (the res-DB
     `EnquiryLoader` path stays primary).
   - Dedupe strategy vs migrated enquiries TBD against the sample —
     likely email + enquiry date (± a small window); must be re-runnable
     without duplicating.

Both importers report per-row skip/error reasons (loader-style summary)
and are safe to re-run.

## Sequencing

- **Entry gate:** Nick's sample sheets (column structure). Nothing beyond
  this skeleton until they arrive.
- The booking import must run **before** the production
  `zoho_backfill --kinds booking` (bookings must exist, with back-stamped
  `created_at`, when the backfill pushes them).
- Contact/enquiry migration (and their Zoho backfill kinds) run first, so
  email-matching and enquiry dedupe have something to match against.

## Acceptance

- Booking import: rows land as CONFIRMED-history bookings with synthetic
  `booking-*` quotations, back-stamped `created_at`, matched-or-created
  persons, matched villas; re-run converges; errors reported, not
  swallowed.
- Enquiry top-up: zero duplicates against res-migrated enquiries on
  re-run.
- Zoho booking backfill after the import carries faithful `booking_date`
  and `is_synthetic` flags.
- `CUTOVER.md` reflects the new order (done 2026-07-29, see §4).

## Dependencies

- **⛔ Nick's sample sheets** — hard entry gate.
- [GAP-082 ✅](done/gap-082-zoho-villa-push.md) — booking push + backfill
  this feeds; supersedes its FULL-booking-load precondition.
- GAP-085 — financials block should be in place before the booking
  backfill runs, or historic bookings push with null financials (decide at
  sequencing time).
