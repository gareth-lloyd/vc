# GAP-107 — Legacy loader: extras never loaded, deleted regions imported, a reconcile count still guessed

- **Severity:** 🟠 Gap (cutover fidelity). Backend `data_migration/` only.
- **Source:** 2026-09-10 sweep of `todo/` for loader follow-ups. Pulls together
  three items that each said "needs its own ticket" and never got one:
  - SPEC-001's "Cutover parity gap" bullet
    (`spec-001-rateplan-date-authority-regime-bucket.md:212–217`).
  - GAP-102's geo-loader note (`done/gap-102-…md:122–127`).
  - GAP-073 live dry-run follow-up #2 (`done/gap-073-…md:22–23`).
- **Files touched (best-guess):**
  - `django_res/data_migration/loaders/pricing.py:534–543`:
    `RateBandLoader.legacy_query` filters `r.IsExTra <> 1`. No loader writes
    `pricing/models/extra.py` `Extra` or `pricing/models/discount.py`
    `Discount`.
  - `django_res/data_migration/loaders/lookups.py:23–55`: `RegionLoader`.
    Its query is `SELECT Id, Name, Slug, CountryId FROM VillaRegion` with no
    deletion filter, and `transform_extra` hardcodes `is_active = True`.
  - `django_res/data_migration/loaders/country.py:44–51`: `CountryLoader`
    reads `IsActive` but no deletion column.
  - `django_res/data_migration/management/commands/reconcile_legacy.py:100`:
    the `Region` check counts every `VillaRegion` row. Lines `:336–353` hold
    the `PropertyFinance` check with `expected_gap=1236`, still marked
    PLACEHOLDER.
  - `django_res/data_migration/CUTOVER.md`: the expected-losses list doesn't
    mention extras or discounts.
  - `django_res_design/todo/done/gap-056-rate-model-restructure-property-period-band.md:124`:
    see the disagreement in §1.

## Problem

### 1. Legacy extras are never loaded, and nothing records the drop

Legacy extras share the rate table: 137 live `VillaSeasonRate` rows carry
`IsExTra = 1` (GAP-056's count). `RateBandLoader` correctly keeps them out of
the rate grid, but nothing else reads them. So every migrated villa starts with
an empty `Extra` table. Staff have nothing to quote, and the GAP-102 villa
`extras[]` catalogue pushes empty for every migrated villa.

Booked extras on legacy bookings are **not** affected: GAP-017's
`BookingChargeItemLoader` ports those from `VillaBookingDetails`. The gap is
the **catalogue**: what a villa offers, not what was sold.

⚠️ **The spec and the code disagree.** GAP-056 (`:124`) says extras "route via
`OldId_ExtraRate`, already handled in `pricing.py`". Nothing named
`OldId_ExtraRate` exists anywhere in `data_migration/`. Either the handling
was planned and never built, or it was dropped without the spec being updated.
Establish which before building anything.

The legacy **discount** columns (`IsDiscount` / `DiscountRate` /
`DiscountType` / `DiscountApply` / `DiscountNight`) aren't read either.
Dropping those is probably right: GAP-009 found legacy stored them but never
applied them (`RatesModel.Calculate()` reads `DiscountType` into an enum and
stops). But `CUTOVER.md` doesn't record the drop, so a reconcile reader can't
tell a deliberate loss from an oversight.

### 2. The geo loaders import deleted legacy regions as active

`RegionLoader` has no deletion filter, so a cutover run loads **71** legacy
regions instead of **57**. Every one of them lands with `is_active = True`,
including ten live-but-orphaned rows hanging off deleted countries ("Villa
Villa Region", "Test Regions", London/England, three Indian regions). The
orphans don't fail to load. They fall back to `unknown_country()` and become
selectable.

They land in every region dropdown: the SPA's geo pickers, the quote builder's
has-properties filter, and the Zoho region sub-objects that carry `is_active`
since GAP-102. GAP-103's first `region` backfill would push the junk once and
then have to retire it again in Zoho.

`CountryLoader` has the same shape of problem to check. It maps `IsActive`
but ignores the deletion column, so a deleted country with `IsActive = 1`
would load as active.

### 3. `PropertyFinance` reconcile count is an unchecked guess

`expected_gap = 1236` is marked PLACEHOLDER. GAP-073's live dry-run on the
24-Apr dump measured **1235**, which makes it a reconcile blocker. The check's
own comment explains the likely cause: GAP-070's owner-contact fallback
creates a `PropertyFinance` row for each villa with no finance record but a
live OWNER assignment. So the true gap is "1236 minus the fallback count",
which the comment says is "only derivable against the live dump". A gap of
1235 fits exactly one fallback row, but nobody has confirmed that.

## Proposed fix

1. **Extras: decide first, then build or record.** This is a product call,
   so surface it rather than picking a side:
   - **Port:** add an extras loader over `VillaSeasonRate WHERE IsExTra = 1
     AND DeletedAt IS NULL` into property-scoped `Extra` rows. It should be an
     idempotent upsert keyed on `legacy_id`, with its date window from
     `FromDate` / `ToDate` (extras are property-scoped with absolute windows,
     per SPEC-001), a registry entry, and a `reconcile_legacy` check. Map
     `ChargeCategory` the way GAP-088 does, and apply the NULL-currency rule
     GAP-056 documented for rates.
   - **Drop:** list the 137 rows in `CUTOVER.md` expected losses, with the
     reason.

   Either way, record the discount-column drop in `CUTOVER.md` (the GAP-009
   rationale), and correct GAP-056's `OldId_ExtraRate` claim.
2. **Regions and countries: never load a deleted legacy row as active.**
   First confirm against the dump which deletion columns (`DeletedBy` /
   `DeletedAt`) `VillaRegion` and `VillaCountry` actually carry.
   - Load a deleted row as `is_active = False` rather than skipping it.
     Villas, enquiries and people may still point at it, and the FK must
     resolve. This is exactly the "retired: readable, not selectable" meaning
     GAP-102 gave `is_active`. No soft-delete column is involved (root
     principle 5).
   - Treat an orphan under a deleted country the same way: inactive, not
     re-homed onto the unknown sentinel as live.
   - If a deleted, **unreferenced** row would be cleaner skipped, that's a
     fine refinement, but it's not needed for correctness.
3. **`PropertyFinance`: explain the 1, then pin it.** Count the owner-contact
   fallback rows on the dump.
   - If they're identifiable (a marker, or derivable from the "no legacy
     `VillaFinance` twin" condition), subtract them in `loaded_count` so the
     gap stays 1236 regardless of the fallback count. That beats a new magic
     number.
   - Otherwise set the measured constant and explain it in the comment.

   Either way, remove the PLACEHOLDER marker.

## Acceptance

- Extras decision recorded in `design/decisions.md`. Then either:
  - an extras loader ports the live `IsExTra = 1` rows, pinned by transform
    tests on dict fixtures (style: `data_migration/tests/test_country_loader.py`)
    and a `reconcile_legacy` check; or
  - the drop is listed with its count in `CUTOVER.md` expected losses.
- The discount-column drop is listed in `CUTOVER.md`, and GAP-056's
  `OldId_ExtraRate` line is corrected.
- A deleted legacy region or country loads `is_active = False`, including
  orphans under a deleted country. (transform tests)
- A new `reconcile_legacy` invariant: zero active `Region` / `Country` rows
  whose legacy twin is deleted. A live dry-run shows 57 active legacy
  regions.
- The `PropertyFinance` gap is explained and pinned, with no PLACEHOLDER left.
  (live dry-run)
- `loadlegacy --all` + `reconcile_legacy` green on the dump; quality gate
  green.

## Dependencies

- **Blocks GAP-103.** The region push kind's first backfill must not ship
  deleted regions.
- **GAP-102** (resolved): its villa `extras[]` catalogue is empty for
  migrated villas until §1 lands.
- **Q-025** holds the other open reconcile placeholder (`Room placement`,
  gap 49). It's kept separate because it needs an owner conversation;
  recalibrate both at the same dry-run.
- **SPEC-001**: its parity bullet now points here. **GAP-009**: the
  discounts rationale. **GAP-017**: booked extras are already ported.
  **GAP-073**: surfaced §3. **GAP-088**: `ChargeCategory` for ported extras.
