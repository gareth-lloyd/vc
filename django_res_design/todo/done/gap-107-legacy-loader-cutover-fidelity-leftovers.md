# GAP-107 — Legacy loader: extras never loaded, deleted regions imported, a reconcile count still guessed

> **✅ RESOLVED (2026-09-10, local `main` unpushed)** — shipped on `feat/gap-107`
> in 4 code units (bd4a7659 geo loaders honour legacy deletion, 3f75ed36 geo
> reconcile parity checks, f8d06eea `PropertyFinance.legacy_id`, b6bddbda
> `Extra.legacy_id` + `ExtraLoader`) plus the extras reconcile check + docs,
> a live dry-run (`DRYRUN_LOG.md` run 3) and this close-out.
>
> **Decision (user, 2026-09-10): extras are PORTED as opt-in.** A new
> `ExtraLoader` over `VillaSeasonRate WHERE DeletedAt IS NULL AND IsExTra = 1`
> writes property-scoped `pricing.Extra` rows: `legacy_id = ID`, kind `OTHER`,
> `FIXED_PER_STAY`, `amount = Price` verbatim, `is_mandatory=False`,
> `commissionable=True`, **no date window** (the `FromDate`/`ToDate` this
> ticket proposed are the 2022 fold-in timestamps — porting them would hide
> every extra from the engine), currency via `resolve_property_currency`.
> Updates touch only name/description/amount; a full run retires ported
> extras that vanished from legacy. Discount columns dropped (GAP-009),
> recorded in `CUTOVER.md` §4i. GAP-056's `OldId_ExtraRate` claim corrected.
>
> **Geo.** `RegionLoader` / `CountryLoader` select `DeletedAt` + `DeletedBy`
> and load a deleted row as `is_active=False` (OR-predicate — either
> convention counts); a region is retired if its own row or its country is.
> Live rows claim an iso2 before deleted duplicates. `--since` now filters on
> legacy's real `CreatedAt` / `UpdateAt` / `DeletedAt` columns.
>
> **Finance.** `PropertyFinance.legacy_id` (migration `properties/0009`) is
> stamped by the per-villa pass; the reconcile `loaded_count` scopes to it,
> so the gap is **1236 = 1089 `VillaId = 0` + 146 on deleted villas + 1 on the
> blank-name villa**, stable regardless of the GAP-070 fallback count. No
> PLACEHOLDER left.
>
> **Live dry-run corrects this ticket's numbers** (they came from the git
> `DbScript.sql`, not the prod dump): **96** live extras (84 load, 12 on
> deleted / blank-name villas), **64** regions with **42** live (not 71/57),
> 6 live countries. Every GAP-107 check passes; the only remaining
> `reconcile_legacy` BLOCKER is the pre-existing Q-025 `Room placement` 49.
>
> ⚠️ **Product-visible at cutover:** legacy deleted the United Kingdom row,
> so **GB retires on load** (readable, not offered in pickers), as do IN, NZ
> and AU; 6 migrated villas sit in retired regions. The 84 ported extras are
> opt-in and **not quotable from the quote builder until GAP-111** wires
> `opt_in_extras`. Run `zoho_backfill --kinds villa` after the load.
>
> Spun off: GAP-111 (builder opt-in extras). Folded into the 2026-09-11
> audit tickets at merge (2026-09-14): `CurrencyLoader` ignoring `DeletedAt`
> → BUG-028 §3; `loadlegacy --since` raising on tables with no `UpdatedAt`
> → BUG-029 §2 (`--since` retired). GAP-103 is unblocked.
>
> **Merge reconciliation with the 2026-09-11 audit (2026-09-14).** The audit
> below was written against `main` before this branch merged, so parts of it
> are superseded by the as-built work above:
> - §1 extras — answered (ported as opt-in, no date windows); Q-028 item 4
>   closed accordingly.
> - §2 geo — counts match the audit (64 / 12 / 42). **User decision
>   2026-09-14: merge as built** — a deleted legacy country keeps its
>   `legacy_id` on the ISO row and retires it (GB, IN, NZ, AU), overriding
>   BUG-030 §7's "attach no `legacy_id` to a live ISO row". The active/retired
>   parity checks GAP-108 planned are already in `reconcile_legacy`. The
>   region remap (25→61, 27→60, BUG-030 §8) is still open and lands on top.
> - §3 finance — the audit's 1235 counts every `PropertyFinance` row; the
>   branch stamps `legacy_id` and scopes the check to it, so the pinned gap
>   is 1236 (the villa-463 fallback row carries no `legacy_id`). GAP-108's
>   §3 item is done by this ticket.
>
> **2026-09-11 audit update (see BUG-028/029/030, GAP-108/109, Q-028).**
> - **§1 extras** — still open; restated as Q-028 item 4 so it rides the next
>   Nick call. The `OldId_ExtraRate` disagreement stands.
> - **§2 geo** — the 71/57 numbers do not match the 24-Apr dump: `VillaRegion`
>   has **64** rows, **12** with `DeletedAt`, **10** live under deleted
>   countries, 42 clean; `VillaCountry` 23 rows, 17 deleted, 10 of those still
>   `IsActive=1`. Recount before pinning the invariant. Two refinements land
>   with BUG-030: a deleted legacy country must not attach its `legacy_id` to
>   a live ISO seed row (today 6→GB, 10→NZ, 11→IN do, so regions 42/44/45/46
>   resolve onto live countries), and the six live villas under deleted
>   regions with live twins are **remapped** (25→61, 27→60; user decision
>   2026-09-11), not left in an inactive region. The invariant "zero active
>   Region/Country whose legacy twin is deleted" is added by GAP-108.
> - **§3 finance** — explained and pinned by GAP-108. The 1235/1236 figures
>   above are the 24-Apr-2025 dump's; on **ResProd** (13-Aug-2026) the pinned
>   gap is **1239**, itemised to a zero residual on the `_Check`: 1597 legacy
>   rows − 413 contact-default templates (`VillaId = 0`, `ParentId` NULL)
>   − 676 parent-child overrides with no villa of their own − 150 rows on
>   villas `live_villa_sql` excludes = 358 stamped per-villa rows. Note the
>   correction to the old reasoning: override rows with `VillaId > 0` **are**
>   ported as the villa's own row, so `ParentId` is not an exclusion.
>   `PropertyFinance.legacy_id` (added here) is what makes the count stable.
>   Closed.

- **Severity:** 🟠 Gap (cutover fidelity). Backend `data_migration/` only.
- **Source:** 2026-09-10 sweep of `todo/` for loader follow-ups. Pulls together
  three items that each said "needs its own ticket" and never got one:
  - SPEC-001's "Cutover parity gap" bullet
    (`done/spec-001-rateplan-date-authority-regime-bucket.md:235–241` — SPEC-001
    closed 2026-09-14 with GAP-110; the bullet still reads the same).
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
`IsExTra = 1` (GAP-056's count — *corrected at close-out: **96** on the
24-Apr-2025 prod dump; 137 was a parse of the git-tracked `DbScript.sql`*). `RateBandLoader` correctly keeps them out of
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
regions instead of **57** (*corrected at close-out: the dump has **64**
regions, **42** live under live countries; 71/57 were the git script's
counts*). Every one of them lands with `is_active = True`,
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
  regions (*measured: 42 — see the banner*).
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
