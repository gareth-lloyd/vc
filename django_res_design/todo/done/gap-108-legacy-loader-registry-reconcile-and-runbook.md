# GAP-108 — Legacy loader: unregister the dead booking loaders, make `reconcile_legacy` prove what it claims, and bring the runbook back to the code

> **✅ RESOLVED (2026-09-16)** — shipped on `feat/gap-108`; fast-forwarded into
> local `main` (unpushed) at close-out. 13 commits:
> 31a903de U1 unregister `Booking`/`Payment`/`BookingChargeItem` (34 → **31**
> loaders) with their three checks **inverted** to `… with legacy_id (must be
> 0)`, so "we load no bookings" is now mechanised rather than asserted;
> 0387357a U2 `suppress_summary_rebuild()` in `BaseLoader.load()` + one
> synchronous rebuild at the end of `loadlegacy` (and `rebuild_summaries` as the
> manual recovery path) — `LLEN celery` is 0 after a load, no worker needed;
> 8211c20b U3 `legacy_active_sql()` — ResProd soft-deletes enquiries, rooms,
> features, collection memberships and nearby places, on legacy's
> **NULL-is-inactive** convention; 271e31b7 U4 `live_villa_sql()` shared by
> `PropertyLoader` and the six villa-scoped reconcile queries; 82b0582f U5
> loaded counts default to `legacy_id__isnull=False` so an organic row can no
> longer mask a loader that loaded nothing (allowlist of 2, with reasons);
> 4e3e8f76 U6 a check for **every** registered loader + the coverage test that
> keeps it that way; f8613f7d U7 structural invariants and the right reasons on
> the gaps; 8797bc9b U7 follow-up; 7a1b3023 U8b, cd3656e2 U8c, c2183132 U8d the
> dry run and its fixes; 5d5299e4 U9 runbook; 860a39bd U10 the remaining docs.
>
> **The headline:** every `expected_gap` is now pinned to the **ResProd**
> (13-Aug-2026) dry run and *itemised to zero residual* — no placeholders, no
> uncomposed numbers. `reconcile_legacy` exits 0 at **54/54** checks with night
> parity 0, and is unchanged by a `createsuperuser`. `_CHECKS` went 44 → 54.
>
> **Three findings worth carrying forward**, all raised by the dry run rather
> than the audit that opened this ticket:
> - The audit's own figures were stale: "30 loaders" was **31**, Room placement
>   49 was **61**, `PropertyFinance` 1235/1236 was **1239** (= 413 contact
>   templates + 676 parent-child overrides + 150 rows on excluded villas).
> - `RateBand`'s legacy-side SQL was counting rows the loader never reads
>   (28 721 priceless, 3 730 on dead seasons/villas), so its "gap" measured
>   nothing. Replaced with the loader's own arithmetic; gap **462**, decomposed.
> - Post-Nov-2025 legacy writes stopped naming `VillaClientDetails`, so
>   **1 423 of 1 541** quotations were landing on the `UNKNOWN_CLIENT`
>   sentinel. U8b recovers the customer from the linked enquiry (user-approved
>   2026-09-15/16). This was invisible to row counts — every row loaded.
>
> **Deliberately not fixed here** (tickets own them): GAP-112 post-load customer
> relink for the 321 sheet-born quotations; GAP-113 `VillaArchiveBookings`
> (272 live stays, 7 ending today or later); GAP-114 `CarriedRates` (6 864
> quotable rows legacy flags as copied-forward-not-confirmed); GAP-115
> `SecurityDepositPaymentMethod` codes nothing we hold decodes; GAP-109 rows
> 18-20 for three ResProd columns no loader reads. `QuotationLine.created_at`
> stays the load day — `VillaQuotationDetails` has no `CreatedAt` — documented
> in `CUTOVER.md` §5. `WORDPRESS_BACKFILL.md`'s Option A-vs-B is **open**: B's
> premise is measurably false (2 856 module/id pairs fan out to >1 site).
>
> Also discharged: GAP-110's three dump-dependent follow-ups (night parity 0,
> every placeholder pinned, 558-line quote sample — 526 exact, 32 explained, no
> engine or loader bug); SMELL-021's "no NET signal exists" corrected (`PriceType
> = 10` on 2 083 live rows) while its GROSS conclusion stands for a better
> reason; Q-025's residual placeholder.

- **Severity:** 🟠 Gap (cutover process). Backend `data_migration/` + docs.
- **Source:** 2026-09-11 legacy-loader audit; live `loadlegacy --all` +
  `reconcile_legacy` on scratch DB `villacollective_loaderaudit`
  (24-Apr-2025 dump). Absorbs Q-025's `Room placement` placeholder, now
  explained. *(It also absorbed GAP-107 §3, but GAP-107 merged on
  2026-09-14 with its own fix — see §2.)*
- **Files touched:**
  - `django_res/data_migration/registry.py:100-110`.
  - `django_res/data_migration/management/commands/reconcile_legacy.py`
    (`_CHECKS`: `:100-114, 160-180, 187, 195, 209, 240, 302, 329, 336-352,
    354-414, 421-436`).
  - `django_res/data_migration/loaders/integrations.py:29-31, 118-119`;
    `tests/test_integrations_loader.py:67-75`.
  - `django_res/data_migration/CUTOVER.md` (§1–§7, §4b, §4c, §4g, §5 table,
    §6), `COVERAGE.md:7, 49-51, 64`, `ACCEPTANCE.md` S2/S6,
    `DRYRUN_LOG.md:210`, `.claude-tmp/drop-and-reseed.sh`.
  - `django_res/CLAUDE.md` §"Legacy data migration" and the two
    `reservations.Guest.merge` citations.
  - `django_res_design/todo/done/smell-021-…` rationale (via a note, not a
    rewrite), `done/gap-056-…:124` (`OldId_ExtraRate`, GAP-107 already flags).

## Problem

### 1. The booking loaders GAP-089 declared dead still run

`registry.py:100-106` runs `BookingLoader`, `PaymentLoader`,
`BookingChargeItemLoader` under `--all`; `AvailabilityBlockLoader`'s comment
(`:107-109`) depends on them; `SyncRecordZohoLoader.SPECS` lists
`VillaBooking`; `_CHECKS` has Booking/Payment/ChargeItem rows and the
Enquiry −8 / Quotation −3 / QuotationLine −2 gaps encode the synthesised
`booking-*` rows. CUTOVER §4's superseded-note says the step "is no longer
part of cutover" while §4g still documents it as live.

The 3 `VillaBooking` rows: Id 1 on villa 1 (Feb 2025, €700, 3 payments, 2
charge lines), Ids 2–3 on villa 462 **"Test Villa for Booking"** (Apr–May
2025). None of their numbers appears in the Past Bookers sheet (BN 1–1153 vs
legacy 1501+), so no duplicate stay — but if loaded they show on calendars
and finance, flip `is_repeat_customer` for clients 1/4/6, and
`zoho_backfill --kinds booking` pushes all three (every status, by design).
Payment status map is also wrong (real values `active`/`paid`; all land
PENDING; method hardcoded CARD vs real SCHEDULED) — moot once unregistered.

**Decision 2026-09-11: unregister.** Modules stay as the schema record.

### 2. `reconcile_legacy` compares what is easy, not what matters

- **Both placeholders are now explained.** `Room placement` 49 = 46 rooms on
  villas not loaded (deleted / blank-name 249) + 3 rooms with a dangling
  `PlacementId` (4 ids absent from `VillaRoomsPlacement`). `PropertyFinance`
  1235: 1 526 = 1 089 `VillaId=0` (413 contact templates + 676 per-season
  overrides) + 146 on deleted villas + 1 on villa 249 + 290 live own rows;
  loaded = 290 + 1 owner-contact fallback (villa 463 Housemartin ← contact
  234; villas 464/466 have no mapping → skipped). **Done by GAP-107
  (merged 2026-09-14):** `PropertyFinance.legacy_id` is stamped by the
  per-villa pass and the check counts only `legacy_id IS NOT NULL`, so the
  fallback row drops out and the pinned gap is **1236** (1089 + 146 + 1),
  whatever the fallback count. The rest of this bullet is the pre-merge
  analysis. Fallback rows carry no
  marker, so pin the constant with this arithmetic.
- **Most checks count organic rows too** (`:100-114, 187, 240, 354-391`:
  User, Region, Currency, Collection, Feature, RatePlan, Quotation, Booking,
  Payment use a bare `count()`). A `createsuperuser` before reconcile turns
  User into a blocker; any staff-created row does the same. Three checks
  already scope to `legacy_id__isnull=False`.
- **No check at all** for ~~`property_feature` (11 955 rows — BUG-030 §11 adds
  it)~~ (✅ BUG-030 U3 added `PropertyFeature`), `property_defaults`, and the satellites PropertyLocation / Capacity /
  Settings / Description, RoomBeds, PropertyService, RatePeriod,
  BookingGuest. ACCEPTANCE S2 says every loader has a check.
- **Right numbers, wrong reasons**: ~~CollectionMembership 308 ("duplicates";
  see BUG-030 §13)~~ (✅ itemised by BUG-030 U3), PropertyContactAssignment 1 ("composite legacy_id
  collapse"; all 335 are unique — it is the mapping on blank-name villa 249),
  ~~GuestPreference 93 (BUG-030 §30)~~ (✅ comment rewritten by BUG-030 U6), Currency 4 (3 junk + the *live* EUR,
  BUG-028 §3), Person (owner/agent) filters `DeletedAt IS NULL` while the
  loader loads deleted contacts INACTIVE (masked: 0 deleted in the dump),
  VillaAvailability narrative (property 133, 2026-07-25 → 08-22) aged out —
  today 0 = 0 trivially (BUG-030 U7 rewrote the comment as a gap rule; the
  number still needs the live dump).
- **Count checks cannot see value regressions.** BUG-028's four defects and
  BUG-029's primary-flag flip (a re-run-only effect, won't-fix under the
  one-shot load) all passed. BUG-028 adds the money invariants;
  this ticket adds the structural ones: primary-e-mail count equals loaded-
  e-mail count; zero active `Region`/`Country` rows whose legacy twin is
  deleted (GAP-107 §2 — GAP-107 already added count-parity checks
  `Region (imported)`, `Region (active)`, `Country (active)`; a row-level
  check is only needed if those counts prove too weak); zero `Property.slug`
  containing `://`.

### 3. The runbook describes a loader that no longer exists

- COVERAGE `:7` "60 tables": the dump has 61 and all 61 are classified.
- ✅ CUTOVER §6 "loaders without `UpdatedAt` silently ignore `--since`": they
  crashed. BUG-029 (2026-09-15) retired the flag and rewrote §1 and §6 (no
  delta mode; late writes = fresh reload from a newer dump).
- CUTOVER §4 IsDefault list omits changeover day (27 villas) and says
  currency ×91 (188 — BUG-028 §2/§3); §4c mentions the `E-{Id:06d}` fallback
  that never fires (✅ wording fixed by BUG-030 U5) and `/api/quotations` (actual `/api/v1/quotations`);
  §3 says check `VillaMaster` while `drop-and-reseed.sh` prints
  `VillaCountry` and hard-codes `live-db-24-apr.sql`, so it cannot reseed the
  final dump §2 produces; "~2 minutes" measured 157 s (199 s on re-run).
- CUTOVER §4b overstates Zoho continuity: `VillaContact.ZohoId` is blank on
  all 233 rows (no contact continuity exists; every contact push at v1.1
  INSERTs), properties 75 (112 raw, 36 on deleted villas), enquiries 44.
  `integrations.py:29-31` cites a `VillaArchiveBooking` table that does not
  exist; `SPECS` still lists two tables without the column and the test pins
  five. → GAP-098 note.
- `django_res/CLAUDE.md` cites `reservations.Guest.merge` twice (Guest is
  retired), describes `BookingLoader` as live, and omits the two sheet
  commands and `reconcile_legacy --integrations`.
- ✅ ACCEPTANCE S6 "loaders that ignore `--since` warn loudly" (replaced by
  the one-shot guard check, BUG-029); DRYRUN_LOG
  `:210` "36/36 rows" vs 33 checks today.
- COVERAGE claims `VillaConciergeServices` maps to TextChoices and that only
  "298 Sea View" has multiple categories (50/229 live features do).
  **Corrected while fixing it (2026-09-16):** the TextChoices claim is half
  right — `reservations.ConciergeTier` *does* exist, on
  `BookingConciergeItem.tier`; what has no home is the **property-level**
  `VillaMaster.ConciergeService` (383 of 386 live villas), which is GAP-109
  row 10. And the multi-category figure on ResProd is **55 of 236** live
  features, not 50/229 — the 24-Apr-2025 numbers. (The "eight categories on
  298 Sea View" was raw mapping rows; only 7 resolve to a real category.)
- SMELL-021's "legacy has no NET/GROSS signal" is wrong (1 931 Net rows on the
  24-Apr-2025 dump; **2 083** live `PriceType = 10` rows on ResProd;
  the GROSS stamp is still the right outcome because legacy quotes
  `WeeklyPrice` verbatim). Note it on the done ticket and in `pricing.py:285-290`.
- GAP-107 §2 "71 vs 57" → 64 rows / 12 deleted / 10 orphans / 42 clean.

### 4. Two load side-effects the runbook should name

- Each full load enqueues **4 086 / 7 577** `pricing.tasks.rebuild_summary_task`
  messages into the real Redis broker via `pricing/signals.py` `on_commit`
  (dev is not eager). On production a worker running during cutover churns
  on ~4–8k tasks per pass. Pause the worker (or suppress the signal inside
  the loader like `suppress_zoho_push`) and run one `rebuild_summary` after.
- Three loads left **61 877** `AuditLog` rows (rateband 17 640, rateperiod
  16 880, propertyimage 12 283, propertyfeature 9 991 …); each `rate_rule`
  full-replace adds ~14k tombstones. Expected, but say so.

## Proposed fix

1. Remove the three booking loaders from `LOADERS`; fix the availability
   comment; drop the `VillaBooking` spec and the 5-table test pin; delete or
   invert the Booking/Payment/ChargeItem checks; Enquiry −8 → −5, Quotation
   / QuotationLine → 0; move `VillaBooking`, `VillaPayment`,
   `VillaPaymentDetails`, `VillaBookingDetails` to "Dropped — GAP-089" in
   COVERAGE; mark CUTOVER §4g superseded like §4's note; keep
   `tests/test_booking_loader.py` and `test_charge_item_loader.py` as
   schema-record tests with a docstring saying so.
2. `_CHECKS`: default `loaded_count` to `legacy_id__isnull=False`; pin Room
   placement 49 with its derivation (PropertyFinance is already pinned at
   1236 by GAP-107); add the
   missing checks (a satellites check can be "one per loaded Property");
   rewrite the wrong reasons; add the structural value invariants.
3. Docs pass over CUTOVER / COVERAGE / ACCEPTANCE / DRYRUN_LOG / CLAUDE.md
   for every item in §3, plus the §4 runbook notes (pause worker, audit
   volume, real timings). Parameterise `drop-and-reseed.sh` on the dump
   filename.
4. ~~Recount GAP-107 §2 and note that §3 closed here~~ (done in GAP-107's
   dry-run 3); note Q-025's placeholder
   closed here; note the Zoho contact fact on GAP-098.
5. **GAP-110 dump checks** (`CUTOVER.md` §5 items 3–5), on the same dry run:
   pin the villa-level `RatePlan` check's `expected_gap` (placeholder `0`)
   with each unresolved villa itemised; run the night-parity section and
   itemise any villa it reports (loader fix or explained loss, never waved
   through); quote a sample of `VillaQuotationMaster` rows on the 37 villas
   with cross-season same-party overlaps and compare against legacy. The
   sample is also the only evidence for GAP-110's unticked "one-plan stays
   quote identically before and after" line — the suite proves projected ==
   materialised, not old-engine == new-engine. A systematic miss means the
   cross-season precedence needs an `is_occ`/season sort key, not a
   per-villa patch.

## Acceptance

- `loadlegacy --all` runs ~~30~~ **31** loaders (the ticket's arithmetic was
  off by one: the registry held 34, not 33, before the three unregistrations);
  `Booking`/`Payment`/`BookingChargeItem` counts are 0 on a fresh load.
- `reconcile_legacy` exits 0 on the dump with no PLACEHOLDER markers left,
  every constant explained in its comment, a check for every registered
  loader, and the value invariants green.
- A `createsuperuser` before reconcile does not change the result.
- GAP-110: `RatePlan` check pinned with a derivation; night-parity reports
  0 villas or every residue is itemised in CUTOVER; the overlap-villa quote
  sample matches legacy (mismatches listed with cause) and its result is
  recorded on `done/gap-110-…`.
- Every §3 line corrected; `grep -n "Guest.merge\|--since\|60 tables"` finds
  nothing stale.
- Quality gate green.

## BUG-030 hand-off (2026-09-15)

BUG-030 changed these reconcile constants and SQL; each is pinned in
`test_documented_expected_gaps_are_encoded` from the audit numbers, and the
live dry run confirms or re-pins them:

- `Country (legacy)` **−228 → −227** (no `UK` row). The dev dump also carries
  a live "Dev Country" (`DC`, Id 25) the prod dump lacks.
- New `PropertyFeature` check, **0 pinned**. Its T-SQL remap has never run
  against SQL Server; the dry run is its first execution.
- `Organisation (agency)` now excludes `NA` / `N/A` / `-` on the legacy side.
- `VillaAvailability (future days)`: legacy side is
  `ISNULL(AvailableStatus, 0) IN (0, 6, 30, 40, 50, 60)`; the gap is
  trimmed days + days on unloaded properties + errored runs (0 pinned).
- Comments only: CollectionMembership 308, GuestPreference 93, Quotation
  (booking-synth rows are now ACCEPTED).
- Constants moved: `HISTORIC_*` and the new `STALE_ENQUIRY_DAYS` (90) live in
  `data_migration/sheets/constants.py`.

Dry-run checklist from BUG-030 (its "live dry run" acceptance moved here):

- [ ] Slugs contain no `://`; 0 `Organisation(name="NA")`.
- [ ] `PropertyFeature` check executes and its gap is itemised; read the
      `data_migration.deleted_feature_unmapped` lines.
- [ ] 0 enquiries CONVERTED from `VillaEnquire`, 14 PROGRESSING; the
      `data_migration.enquiry_stale_cutoff` line shows the cutoff and count;
      enquiries link to the ~28 + 4 matchable Persons.
- [ ] Quotation lines carry the master's occupancy; quotations back-dated
      (all 19 real ones EXPIRED).
- [ ] `data_migration.preference_quotation_unresolved` count (audit: 126).
- [ ] Availability: status-0 runs load; `trimmed_days` in the summary line
      explains the gap.
- [ ] Regions 25/27 remapped (`data_migration.region_remapped`); decide
      whether **region 47** needs `"47": "61"` if enquiries sit under it.
- [ ] Decide whether the deleted country twins **13 (France) / 20 (India)**
      should alias like England (would move `Region (active)`).
- [ ] After §5 passes, run the CUTOVER §6g Person merges and confirm the
      counts move exactly as listed there.

## Dependencies

- Sequence after **BUG-028 / BUG-029 / BUG-030** (BUG-029 ✅ 2026-09-15) — they move most of the
  constants this ticket pins; do the pinning last on one dry-run.
  **BUG-028 landed 2026-09-14** (DRYRUN_LOG run 4): `RateBand` re-pinned at
  4492 with a zero-residual itemisation. Its dry run gave item 5 a head start:
  the villa-level `RatePlan` check is 261/260 and night parity lists one
  villa, both **villa 249** (the blank-name `VillaMaster` row `PropertyLoader`
  skips — both legacy queries lack the name filter): mirror the filter or pin
  1. `Room placement` is still 49. The rate-row `DeletedAt`/`DeletedBy`
  asymmetry (0 rows differ on this dump) belongs in the doc pass.
- **GAP-110** (landed 2026-09-14) regroups `RatePlan` (521 → ~276) and adds
  the night-parity invariant; its three dump-dependent checks are fix item 5.
- **GAP-107** (resolved, merged 2026-09-14): shipped §1 extras, §2 retired
  geo rows and §3 finance. **Q-025**: its reconcile residual closes here.
  **GAP-098**: Zoho contact note. **GAP-103**: unblocked by GAP-107.
