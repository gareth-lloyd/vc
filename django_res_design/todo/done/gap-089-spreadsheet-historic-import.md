# GAP-089 — Historic import pivot: bookings from spreadsheets, enquiry top-up

> **✅ RESOLVED (2026-09-02)** — built on `feat/gap-089` once the two
> sheets arrived (`Enquiries - FINAL.xlsx`, `VC Past Bookers Final.xlsx`;
> gitignored under `data_imports/`). The sheets changed the design below
> in three places, each user-confirmed 2026-09-01:
>
> 1. **Stays are `reservations.PastStay` rows, not Bookings.** The Booking
>    History sheet has a villa, a year and a `BN…` number per stay — no
>    dates, no money, no email — so a Booking (real dates, occupancy,
>    currency, terms) would have to be faked and would show on calendars
>    and finance. `PastStay` is the honest minimal record: surfaced on
>    Customer-360 as "Past stays", counted into `is_repeat_customer`, the
>    `contact_types` CUSTOMER badge, `/clients?repeat=true` and the
>    owner-portal `is_repeat_guest` (linked stays only). The synthetic
>    `booking-*` quotation + `created_at` back-stamp design is therefore
>    **not used for bookings**, and past stays are **not pushed to Zoho**
>    (deferred — raise the shape with Limitless; `booked_region_slugs` in
>    the clients directory also ignores them).
> 2. **Undated enquiry-sheet rows are contact exports**, not enquiries
>    (1,245 rows, 1,237 with neither villa nor notes): they land as a
>    Person with one provenance notes line. Dated rows become create-only
>    `Enquiry` rows keyed `sheet-enquiry-…` with an explicit `E-SHEET-…`
>    reference, `status=DEAD / lost_reason=UNKNOWN / lead_status=COLD`
>    (assumption: every ≤2024-12 sheet row is dead — one constant to
>    change) and `created_at` back-stamped to the sheet date. No
>    res-vs-sheet enquiry dedupe: measured against the April-2025 snapshot
>    the sources are complementary in time (res 2024-11-14…, sheet
>    …2024-12-09, 30 shared emails, none within 60 days). `EnquiryLoader`
>    now back-stamps its rows from legacy `CreatedAt` for the same date
>    coherence (needs one FULL `loadlegacy enquiry` to repair earlier loads).
> 3. **Tags extend `PersonTag`** with `hnw` ("High net worth") and `owner`
>    ("Villa owner"); VIP/VIP?→vip, PA→pa, Trade→trade, NC→nicks_friend,
>    NWC→nicks_network; unknown tokens (LC, HWC) go to `Person.notes`.
>    ⚠️ The Zoho contact payload pushes tags verbatim, so Limitless's Flow
>    will now see `hnw` / `owner` — tell them (same class as the GAP-093
>    `category` note); whether `hnw` belongs in `SENSITIVE_TAGS` is an
>    open call. `PersonTag.OWNER` is a sheet fact, not a
>    `PropertyContactAssignment` — the Owner *type* badge stays derived
>    from assignments.
>
> Person matching (both importers): `sheet-person-{sha1(email|first|last)}`
> key → email + last-name agreement over ACTIVE people (same email,
> different last name = spouse → second Person; blank names = e-mail-only
> row) → exactly-one ACTIVE name match (customers preferred) → create.
> Matched people are **blank-filled only**, so operator edits survive
> re-runs; a person anonymised after an earlier run is skipped. Villa
> match: exact normalised name / display_name with "Villa " prefix
> tolerated, else **unlinked and tallied** (report, don't guess); region:
> exactly one `(country, name)` hit with the country resolved through the
> alias map. `reconcile_legacy` excludes every `sheet-` row; the Zoho
> backfill's contact + enquiry kinds push the sheet people and the ~2.4k
> DEAD enquiries by design.
>
> **Dev-DB run 2026-09-02** (seed_dev data, so villa/person match rates
> are not meaningful — the seed villas are fictional):
> `import_enquiry_sheet`: 3,624 rows read → 2,376 enquiries + 3,617
> people created, 1,245 undated rows person-only, 3 rows rejected
> (invalid e-mail). `import_past_bookers` (run after the enquiry sheet):
> 1,484 rows read (637 contacts + 847 stays) → 621 people created + 7
> matched onto enquiry-sheet people (blank-filled) + 762 past stays
> created, 85 stays skipped (person not resolvable: sheet-only "Nick
> Corrie" ×5, mangled names like "Jemima Khan (Goldsmith)"), 7 unresolved
> mailing countries, 1 bad year kept as a note, 1 invalid e-mail dropped.
> Re-running both: 0 created, 2,376 enquiries and 762 stays reported
> `exists`, the same skips.
>
> Shipped as: `b7858823` deps · `45e99297` tags · `af3b19fc` helpers ·
> `7d5633af` PastStay · `afcbee88` EnquiryLoader back-stamp · `b674b559`
> reconcile · `71f2cbb5` FE · `40d9795a` review hardening · `10b88fc7`
> `import_past_bookers` · `b409a013` `import_enquiry_sheet`. `CUTOVER.md`
> §4 carries the run order.

- **Severity:** 🟢 Gap (cutover-path change). ~~**⛔ BLOCKED on Nick's sample
  sheets** (column structure) — design past the skeleton below waits for
  them.~~ Sheets arrived 2026-09-01; see the resolution block above.
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
- [GAP-082 ✅](gap-082-zoho-villa-push.md) — booking push + backfill
  this feeds; supersedes its FULL-booking-load precondition.
- GAP-085 — financials block should be in place before the booking
  backfill runs, or historic bookings push with null financials (decide at
  sequencing time).
