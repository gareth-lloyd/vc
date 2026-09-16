# GAP-113 — `VillaArchiveBookings`: 272 staff-re-keyed stays that no loader reads

- **Severity:** 🟡 Gap (cutover fidelity). The table is the only place in
  ResProd holding these stays with dates, amounts and guest contact details;
  nothing loads it, so they reach the new system only as whatever the Past
  Bookers spreadsheet carries.
- **Source:** GAP-108 planning + dry run, ResProd (13-Aug-2026), 2026-09-15/16.
  Deferred from GAP-108 by decision 4 ("classify in COVERAGE only").
- **Files touched:** a new loader under `data_migration/loaders/`, its
  registry entry and reconcile check; `COVERAGE.md`; `CUTOVER.md` §4/§5.

## What the table is

`VillaArchiveBookings` is one of the 13 tables ResProd added since the
24-Apr-2025 dump. It is staff re-keying the Past Bookers spreadsheet back into
the legacy app — **not** an archive of `VillaBooking` (that table was
unregistered as dead by GAP-089/GAP-108: of its 251 rows only 77 are live, and
**76 of those 77 sit on test villas** — the one live booking that does not is
the single row anyone re-opening that decision should look at).

Measured on ResProd 2026-09-16:

| | |
|---|---|
| Rows | 295 total, **272 live** (`DeletedAt IS NULL`) |
| Distinct villas | 102 |
| Stay dates on live rows (`FromDate`) | 2025-03-08 → 2027-09-06 (2024-02-01 is a soft-deleted row) |
| Live rows with a guest e-mail | 258 |
| Live rows with a non-zero `Amount` | 261 |
| Live rows with a `ZohoId` | 81 |
| Live rows whose `Notes` cite a `BN…` quote number | 178 |

⚠️ **The name is misleading and this matters.** Despite "Archive", **7 live
rows end on or after today** (latest `ToDate` 2027-09-13, e.g. `BN1094`
2027-01-03 on villa 418). Anything built here must not assume the rows are
historical — a future-dated row is a live commitment, and dropping it silently
loses a booked stay.

The row carries the guest inline rather than by FK: `Title`, `FirstName`,
`LastName`, `Email`, `CountryCode`/`MobileNo`, `ContactMethod` and a full
postal address, plus `Adult`/`Children`, `Amount`/`CurrencyId` and `Notes`.

## The decision this ticket exists to force

Three options, in increasing cost:

1. **Record the drop.** One line in CUTOVER's expected-loss list. Cheapest,
   and defensible *only* if the Past Bookers sheet is confirmed to cover all
   272 — which has not been checked, and cannot cover the 7 future stays if
   the sheet is a past-bookers export.
2. **Enrich only.** Use the table to fill gaps in sheet-imported stays —
   match on the `BN…` quote number in `Notes` (178 rows have one) and
   backfill amount/party/contact where the sheet is silent. No new stay rows.
3. **Load as the source of past stays**, with the sheet as the secondary
   source. Most faithful, most work: needs a person-resolution rule for the
   inline guest (reuse the sheet importer's matcher, do not invent a second
   one) and a dedupe rule against sheet-imported stays.

**Start by measuring the overlap**: how many of the 272 already exist as
sheet-imported stays, keyed by the `BN` number and by (villa, dates). That
number decides between 1, 2 and 3, and it is a single query away.

## Acceptance

- The overlap against the Past Bookers sheet import is measured and recorded.
- One of the three options is chosen and recorded in `design/decisions.md`
  with its reason.
- The 7 current-or-future rows are explicitly accounted for — loaded, or
  named individually in the drop record. They may not be waved through with
  the past ones.
- `COVERAGE.md` moves the table out of "deferred" into its real
  classification.

## Dependencies

- The Past Bookers sheet import (`import_past_bookers`) defines what already
  lands; this ticket is scoped against it, so it runs after that import in
  the cutover order.
- GAP-098 owns Zoho id matching — the 81 `ZohoId` values are its problem, not
  this ticket's.
