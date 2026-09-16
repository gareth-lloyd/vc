# Dry-run log — legacy loader hardening

Working doc for the bullet-proofing effort (worktree `legacy-loader`,
branch `feat/legacy-loader`). Judged against `ACCEPTANCE.md`; coverage in
`COVERAGE.md`.

> **RECONCILIATION OUTCOME (GAP-073, 2026-07-06).** This log records the full
> effort on `feat/legacy-loader`; `main` diverged (GAP-070 dropped property
> groups, GAP-065 did room placement) so only part of it was replayed onto
> `main`. **Landed:** web-copy preservation, `availability_block` loader,
> Zoho/Temenos hardening (gap 1), `loadlegacy` crash isolation, RateBand 3805
> calibration + PersonEmail/Phone slice fix + guest-pref load-order fix, the
> role-code fix (already on main), `BookingHold.legacy_id`, and these standards
> docs. **Dropped (owner call):** the VillaContactGroupMap → PropertyContact-
> Assignment expansion (Decision 4 below) and the branch's GAP-065 room
> placement (main's wins). **Deferred to a separate finance investigation:**
> the `IsDefault*` finance/settings default resolution (loader bugs 5–6 below),
> the commission/deposit type-code re-key and the VillaCurrency duplicate-code
> resolver — they targeted the now-deleted `GroupFinance` and must be re-aimed
> at GAP-070's `PropertyDefaults`. Read the below as branch history, not the
> as-landed state of `main`.

> **ONE-SHOT LOAD (BUG-029, 2026-09-15).** `loadlegacy --since` is retired and
> in-place second runs are unsupported: `loadlegacy --all` is a one-shot into a
> fresh, migrated DB and refuses an already-loaded one. The historical
> "second run / idempotent / byte-identical" checks recorded below predate that
> decision.

## Environment (current — runs 5 onwards)

- Legacy: `res-db` container (Azure SQL Edge), DB **`ResProd`**, restored from
  `ResSystem/NewResSystem_2026Aug13.bak` (13-Aug-2026 production data, 73
  tables, 545 `VillaMaster` rows).
  `LEGACY_DATABASE_URL='mssql://sa:ResLocal%212026@localhost:11433/ResProd'`
- Reseed: `.claude-tmp/drop-and-reseed.sh <dump-file> [db-name]` — takes the
  dump path and target DB name, restores a `.bak` with `RESTORE … WITH MOVE`,
  and prints the `VillaMaster` count as its landing check (`CUTOVER.md` §3).
- Target: a **fresh** `villacollective_gap108b`/`c`/`d` on localhost:55432
  (villa/villa), migrated then loaded once — `loadlegacy --all` is a one-shot
  (BUG-029), so every re-run is a new DB.
- Ad-hoc legacy SQL: as below, but `-d ResProd` and with `-b` (without it a
  T-SQL error still exits 0).

## Environment (runs 1–4 — historical)

- Legacy: `res-db` container (Azure SQL Edge), DB `NewResSystem` from the
  24-Apr-2025 prod dump (`live-db-24-apr.sql`, since deleted), survived in the
  `ressystem_res-db-data` volume.
  Start: `docker compose -f <main-repo>/ResSystem/docker-compose.yml up -d db`
  (service is `db`, container `res-db`). Port 11433.
  `LEGACY_DATABASE_URL='mssql://sa:ResLocal%212026@localhost:11433/NewResSystem'`
- Target: `villacollective_legacy_dryrun` on localhost:55432 (villa/villa),
  freshly migrated.
  `DATABASE_URL=postgres://villa:villa@localhost:55432/villacollective_legacy_dryrun`
- Ad-hoc legacy SQL:
  `docker run --rm --platform linux/amd64 --network ressystem_default mcr.microsoft.com/mssql-tools bash -c '/opt/mssql-tools/bin/sqlcmd -S res-db,1433 -U sa -P "ResLocal!2026" -d NewResSystem -h -1 -W -Q "…"'`
- Logs: scratchpad `loadlegacy-run1.log` / `reconcile-run1.log`.

## Run 1 — 2026-07-05

`loadlegacy --all` exit 1; `reconcile_legacy --integrations` exit 1.

### Defects found (fix queue, ordered)

1. **`SyncRecordZohoLoader` crashes on live schema** —
   `VillaQuotationMaster` and `VillaBooking` have **no `ZohoId` column** in
   the prod dump (only `VillaContact`, `VillaEnquire`, `VillaMaster` do).
   `loaders/integrations.py:103` raised; same crash in
   `reconcile_legacy.py:403` `_zoho_continuity_section`. CUTOVER §4b and
   `08-integrations.md` assume five ZohoId tables — wrong for this schema.
   Fix: probe `sys.columns` (or INFORMATION_SCHEMA) per table and skip+log
   absent ones, in BOTH the loader and the reconcile section; update
   CUTOVER §4b.
2. **No per-loader crash isolation** — the Zoho crash aborted the whole
   `loadlegacy --all` run mid-command (after the last loader, luckily).
   A mid-registry crash would leave a half-loaded DB with no summary and no
   sequence sync (the "high-water mark" line never printed). Fix: wrap each
   loader in try/except in `loadlegacy.handle`, report per-loader status,
   exit non-zero at the end; always run the sequence sync for whatever
   loaded.
3. **`PersonEmail` / `PersonPhone` reconcile checks are BLOCKER (gap −30
   each)** — loaded 252/195 vs legacy 222/165. Cause (hypothesis to verify):
   the loaded count includes the ~30 channels `ClientLoader` reconciles onto
   client-Persons (GAP-045), while the legacy side counts only
   `VillaContactEmail`/`VillaContactTele`. Fix: exclude channels whose
   person is in the `client-` slice (mirror the Person check split), or add
   the client-side legacy counts. Verify the 30/30 decomposition first.
4. **`RateBand` expected_gap placeholder wrong** — actual gap 3805 (legacy
   7333, loaded 3528) vs placeholder 3727. Do NOT just update the number:
   decompose per ACCEPTANCE S2 using the run counters
   (`rate_rule_overlaps_resolved`: trimmed=2260 dropped=0
   shadowed_dropped=264 party_clipped=3 rule_fragments=27
   periods_created=3376) plus skip reasons (junk dates, priceless non-POA,
   invalid bands, 67 unloaded seasons' rows, occupancy expansion ±). Then
   pin the calibrated value with an itemised comment.

### Reconcile run-1 table (live dump)

All OK except the rows above. Notable calibrated-OK gaps: Currency 4,
CollectionMembership 308, Room 307, PropertyImage 806, PropertyNearbyPlace
77, RatePlan 67, PropertyFinance 1236, Property 1, VillaMaster booking-side
counts tiny (3 bookings / 19 quotations / 3 payments / 2 charge items —
money-parity checks exercise almost nothing on this dump).

## Fix pass 1 — 2026-07-05 (uncommitted, in working tree)

Items 1–3 of the fix queue implemented TDD-first (205 data_migration tests
green, ruff + mypy clean):

- **Zoho column tolerance**: `zoho_id_column_exists()` probes
  INFORMATION_SCHEMA per table; loader skips absent tables with
  `data_migration.zoho_column_missing` warning; reconcile renders a
  non-blocking "no ZohoId column" row. Live: `syncrecord_zoho` created 119 /
  skipped 1005; `--integrations` clean for column-less tables.
- **Crash isolation**: each loader in `loadlegacy` now try/except'd; crash
  becomes a `<loader crashed>` error row; summary + `sync_quotation_sequence`
  always run; `CommandError` after the summary if any loader crashed or
  reported errors. NOTE behaviour tightening: previously exit 0 on reported
  errors, now non-zero.
- **Channel slice**: PersonEmail/PersonPhone checks exclude
  `contact.legacy_id` starting `client-` (decomposition verified: exactly
  30/30 client-reconciled channels; both checks now gap 0 OK).

New finding — **duplicate ZohoId in legacy data (accepted-gap candidate)**:
`VillaMaster` 88 and 339 are BOTH named "Temenos" (status 4), sharing
`ZohoId=577032000002128026`. Both load as separate Properties; the
SyncRecord attaches to the first (legacy 88 → property pk 71); the second is
recorded as a loader error by design → Zoho continuity gap 1 on VillaMaster.
Treatment: document as accepted gap (duplicate legacy villa), flag the
duplicate Property for post-cutover `merge`. Needs user sign-off.

## RateBand calibration — 2026-07-05

`expected_gap` recalibrated 3727 → **3805** with a fully balanced, SQL/replay
verified itemisation (zero residual) pinned as a comment in
`reconcile_legacy.py`. Notables: 2477 priceless non-POA legacy rows (the
dominant bucket), 985 rows on seasons with no RatePlan, the ±108 occupancy
expansion cancellation is a dump coincidence.

**CUTOVER BUG-013 item 2 (band-vs-simple precedence) — CLOSED, verified.**
Exactly one season in the dump (632) has both shapes overlapping; the
approved occupancy bands WON (simple rows 4908/4909 shadowed — a genuine
legacy price ambiguity resolved by the documented approved-first policy).
All 16 shadowed occ bands lost only to identically-priced duplicates; no
distinct band price lost anywhere. An `is_occ` precedence key would change
nothing — not added.

## Coverage-blocker verdicts — 2026-07-05 investigation

Full detail in COVERAGE.md (updated). Summary: availability = drop grid +
build `AvailabilityBlockLoader` for future non-available runs (statuses
30/40/50/60, coalesced per property; 1 block on this stale dump — property
133 booked 2026-07-25→08-22 — but count is dump-relative); images-description
table is per-villa website section copy, NOT captions (Interior/Exterior →
image descriptions, trivial join; WebDesc/Location + 31 video URLs =
DECISION); rooms placement = GAP-065 (1,819 rooms hardcoded MAIN_HOUSE —
load); website-pricing min/max = stale cache, drop; POA flag (16 live
villas, curator-set, no home) = DECISION; ConfigEmail/General = drop
(provision the one real SMTP profile manually — secrets don't ride the
migration); ConfigPropertyDefault = CANNOT drop until IsDefault resolution
lands (below); ContactMap = drop (10 property-less role tags lost);
ContactGroupMap = 19 edges / 38 links exist ONLY here = DECISION, lean
load-as-assignments; PaymentStatus = misnamed gateway webhook log from the
Feb-2025 payment trial, drop.

**NEW LOADER BUGS (live correctness, fix queue items 5–6):**

5. **[FIXED — BUG-028, run 4]** **IsDefault* resolution never implemented.** Legacy
   (`PropertyService2.cs:668-688`): when a villa's `IsDefault*` flag is set,
   the `VillaConfigPropertyDefault` value OVERRIDES the stored column.
   Measured on live villas: min_nights loads 1 instead of effective 7 for
   **197 villas**; commission loads 0% instead of effective **20%** for 68
   finance rows (money!); currency loads None instead of EUR for 91 villas.
   Fix in PropertyLoader/finance loaders (read the single CPD row as
   constants), then the table itself is droppable.
6. **[FIXED — BUG-028, run 4]** **`_COMMISSION_TYPE_MAP = {1: PERCENT, 2: FIXED}`** but legacy
   `CommissionTypeId` values are 0/10/20 (1,509 rows = 10) →
   `commission_calculation_type` loads None everywhere. Fix map to
   10→PERCENT, 20→FIXED (verify 20's meaning against legacy code first).

## Fix pass 2 — 2026-07-05 (uncommitted)

- **Image captions (COVERAGE item 2, load half)**: `PropertyImageLoader`
  LEFT JOINs `VillaPropertyImagesDescription` (MAX(Id) subquery pins the
  join — 10 junk `VillaId=0` dupe rows would otherwise fan out); slot text
  fills blank descriptions (own Description wins; 0/1,226 flagged images
  have one today). Live: descriptions 2 → 1,117 (gap vs dump's 1,177 =
  flagged images on the 806 skipped rows — consistent).
- **GAP-065 placement (COVERAGE item 3)**: `RoomPlacement` +COTTAGE/
  BUNGALOW/STUDIO; `Room.placement` now blank-able (no more MAIN_HOUSE
  lie); new `Room.placement_note` preserves the raw label verbatim
  (migration properties/0029). Live: main_house 1402 / guest_house 131 /
  other 91 / annex 65 / cottage 54 / bungalow 30 / blank 17 / studio 1;
  note on 1,774 rooms. Deferred: floor axis (no data source in this table —
  ticket's floor evidence needs re-investigation), serializer/FE exposure.
  ⚠️ **FE cutover blocker**: `frontend/src/features/properties/schemas.ts`
  zod-enums placement — new values + blank "" fail parsing until updated.
- Tests: 227 data_migration + 312 properties green; ruff/mypy clean.

- **Availability loader (COVERAGE item 1)**: new `availability_block`
  loader → `BookingHold(reason=MANUAL, source-less, expires_at NULL)` —
  chosen over OwnerBlock because every availability read goes through
  `BookingHold.live_overlapping`, the source-or-reason constraint permits
  it, and MANUAL is operator-editable; legacy status preserved in notes
  (status-echo junk notes dropped). `BookingHold.legacy_id` added
  (reservations/0039). Future statuses 30/40/50/60 coalesced per property
  into half-open holds keyed `avail-{prop}-{start}`; full-replace purge;
  `--since` ignored w/ warning; skip-not-error for unloaded properties or
  ranges occupied by imported bookings/staff holds. New reconcile check
  "VillaAvailability (future days)" on day arithmetic (29=29 OK live);
  registered after charge items, before Zoho. Double/triple-run converges.
  241 data_migration + 873 reservations tests green.

## Runs 2–3 — 2026-07-05 (definitive verification)

Run 2 (fresh DB, all fix passes in): load exit 0, **0 errors across 35
loaders**, quotation sequence synced to 2079; reconcile exit 0, all checks
OK. But the **double-run convergence check caught a real bug**: second load
created 16 `guest_preference` rows — the loader ran BEFORE quotations
existed (registry order), so quotation-linked preferences resolved
`quotation=None` on a fresh single pass and were swallowed by the duplicate
collapse; they only appeared on run 2. A one-pass cutover would have
silently under-loaded them, and no reconcile check existed to notice.

Fixes: registry reorder (preference loaders now after `quotation_line`,
with a comment telling the story) + two new reconcile checks
(GuestPreferenceType gap 0; GuestPreference expected_gap=93 — the
duplicate-triple collapse, calibrated).

Run 3 (fresh DB, after reorder): single pass loads **74** preferences
(93 skipped duplicates — matches calibration exactly); reconcile exit 0,
**36/36 rows OK** *(36 was the whole of `_CHECKS` on 2026-07-05; it is **54**
today — see run 5. Read this as that run's result, not the current size of the
table.)*; second load creates rows ONLY in the two by-design
full-replace loaders (rate_rule 3501 + availability_block 1), 0 errors;
second reconcile exit 0 and **byte-identical** to the first.
ACCEPTANCE S2 (green reconcile, calibrated gaps, every loader checked) and
S6 (idempotency, order safety) now hold on this dump.

## Fix pass 3 — 2026-07-06 (product decisions resolved + role-code bug)

The four open product decisions were worked through with the user and
resolved; implementing decision 4 surfaced a further latent loader bug.

- **Decision 1 — Temenos (ACCEPT).** VillaMaster 88 (*Templos*) and 339
  (*Kioni*) are DISTINCT villas sharing one ZohoId — a source-side Zoho error,
  not duplicate records (my earlier "merge candidate" framing was wrong). Both
  migrate; the SyncRecord link is now forced onto the lower Id (88) by an
  `ORDER BY Id` in the Zoho loader query so it's reproducible. Flagged to CRM;
  gap stays 1 until Zoho is fixed. (integrations.py + tests.)
- **Decision 2 — web copy (PRESERVE ALL).** `WebDesc1/2` (298 villas) →
  new `DescriptionSection.WEB_DESCRIPTION`, `Location1/2` (276) → new
  `LOCATION`, `VodeoUrl` (31) → new `Property.video_url` (URLField). Content
  verified distinct from the migrated `OverView`. `PropertyLoader` MAX(Id)
  LEFT JOIN de-fans the non-unique (315 rows / 305 VillaId) table. Migration
  properties/0030; 6 new tests.
- **Decision 3 — property POA (DEFER).** 18 villas; documented as a tracked
  open cutover item (COVERAGE item 4 + CUTOVER §4h) with the regression risk
  and resolve-later recipe. No code.
- **Decision 4 — VillaContactGroupMap (prototyped LOAD by expansion, then
  DROPPED at GAP-073 reconciliation, 2026-07-06).** A `GroupContactAssignment-
  Loader` was built on the branch to expand the **38 net-new** group-only
  contact→property links into `PropertyContactAssignment`
  (legacy_id `grpmap-{group}-{contact}-{property}`, SQL-side `NOT EXISTS`
  dedup, role via `_role_for`, self-calibrating reconcile check). Post-GAP-070
  the product has no groups; the owner dropped the expansion, so this loader,
  its reconcile check, the direct-check `grpmap-` exclusion and its 6 tests
  were NOT replayed onto `main`. The 19 edges (38 links) remain recoverable
  from the archived dump.

- **Loader bug 7 — role-code scale mismatch (caught building decision 4).**
  `VillaRoles` has both `Id` (1–5) and `Code` (10/20/40/50/80). The role FKs
  in the dump — `VillaContactRoleMapping.RoleId` AND `VillaContactMap.RoleId`
  — store the **Code**, but `_ROLE_MAP` keyed on the **Id**, so `_role_for`
  fell back to OWNER for every real row. This mis-migrated **~197/335** direct
  assignments (all 19 Agents, 9 Villa Admins, 131 Villa Managers, 38
  Management Companies → silently flattened to Owner) — a pre-existing bug in
  `PropertyContactAssignmentLoader`, not introduced by decision 4. Fixed by
  re-keying `_ROLE_MAP` on Code (10→Owner 20→Agent 40→Villa Admin 50→Villa
  Manager 80→Mgmt Company); updated `test_role_for_maps_verified_legacy_villaroles`
  and the group-loader test off the stale 1–5 scale. Row counts unchanged (the
  reconcile checks count rows, not roles), so no recalibration; the is_primary
  "one primary per (property, role)" tiebreak now groups by the correct role.

## Open product decisions for the user

*(All four resolved 2026-07-06 — see Fix pass 3 above. Kept for history.)*

1. Temenos duplicate ZohoId → accepted gap 1 + post-cutover property merge.
2. WebDesc1/2 + Location1/2 website copy (297/276 villas) + 31 VodeoUrl
   video links — add DescriptionSection values / a video field, or accept
   loss (recoverable from archived dump)?
3. Property-level POA (16 live villas curator-flagged, no schema home) —
   add a flag (e.g. PropertySettings) + tiny loader, or start showing
   prices?
4. VillaContactGroupMap's 19 group-scoped edges (38 contact×property links)
   — expand into PropertyContactAssignments (role from VillaContactMap or
   default), or drop?

## Coverage blockers (see COVERAGE.md §BLOCKERS)

*(All resolved in the 2026-07-05/06 verdicts above — kept for history. Row
counts here are the 24-Apr-2025 dump's.)*

- `VillaAvailability` 57,389 rows — **no loader, no decision**; with only 3
  legacy bookings, current availability state lives ONLY here. Product
  decision needed (import future-dated non-available days as blocks?).
  Quantify future-dated non-available rows first.
- `VillaPropertyImagesDescription` 315 — captions not read by
  PropertyImageLoader; docs claim "folded into PropertyImage". Join it in or
  record drop.
- `VillaRoomsPlacement` 46 / `VillaWebsitePricing` 441 (POA flag may be
  curator-set) / `VillaConfigEmail` 20 / `VillaConfigGeneral` 10 /
  `VillaConfigPropertyDefault` 1 — inspect + classify.
- `VillaContactMap` 230 / `VillaContactGroupMap` 46 — "duplicate" claim
  unverified; run edge-coverage queries.
- `VillaPaymentStatus` 24 rows — eyeball (24 is big for a status lookup).

## Resolved

- CUTOVER §4f role-source warning: live `VillaContactMapping` has NO
  `RoleId` column; 3/335 mappings lack a role child (→ owner fallback,
  acceptable); GroupId/IsAccess*/IsNotify*/Notes all zero-use in prod.
  CUTOVER.md to be updated.

## Still to do after fix queue

*(The 2026-07-05 queue — **closed**, kept for history. The load+reconcile ran
green in runs 2–5; the idempotency / second-run items are void under the
one-shot rule (BUG-029, banner above), which also retired `--since` and the
`_apply_since` work below; CUTOVER.md was rewritten wholesale in GAP-108
Unit 9.)*

- Re-run full load+reconcile to green.
- Idempotency: second `loadlegacy --all`, diff reconcile + row counts.
- Verify quotation-sequence high-water line prints and next organic number
  is above imported range.
- S3 fidelity spot checks + aggregate invariants (write scripts).
- Band-vs-simple precedence spot check (CUTOVER BUG-013 item 2).
- `--since` append on loaders whose source lacks `UpdatedAt` (inventory
  flags payment/contact_email/etc. as risky) — test one, fix `_apply_since`
  if it produces invalid SQL.
- Update CUTOVER.md (§4b Zoho tables, §4f closure, reconcile table numbers).

## Run 2 — 2026-07-06 (GAP-073 reconciled branch, feat/gap-073)

Live dry-run of the reconciled loaders against the same 24-Apr-2025 dump
(`res-db`), fresh `villacollective_legacy_dryrun` DB migrated to the branch
leaves (properties/0033, reservations/0039).

- **`loadlegacy --all` → exit 0, zero errors on every loader.** Notable rows:
  `property_image` 12283, `room` 1791, `property_contact_assignment` 334 (no
  `grpmap-` slice — GroupMap expansion dropped), `guest_preference` 74
  (registry reorder now runs it after QuotationLine), `availability_block`
  **1** (property 133's single future run, 2026-07-25..08-22), `syncrecord_zoho`
  119.
- **`reconcile_legacy --integrations` — every GAP-073 check passes on live
  data:** `RateBand` 7333/3528 gap **3805 = expected** (calibration confirmed
  against real data); `VillaAvailability (future days)` 29/29 gap 0;
  `GuestPreference` 167/74 gap 93; `PersonEmail`/`PersonPhone` gap 0
  (client-slice exclusion); `PropertyContactAssignment` 335/334 gap 1 (direct
  slice only); Zoho `VillaMaster` gap **1** (Temenos pair) OK, `VillaContact`/
  `VillaEnquire` OK, `VillaQuotationMaster`/`VillaBooking` render **"no ZohoId
  column"** (the INFORMATION_SCHEMA probe — no crash).

### Two PRE-EXISTING blockers surfaced (NOT GAP-073 — main's own checks/loaders,
### untouched by this branch; `finance.py` diff vs main is empty, RoomLoader kept whole)

1. **`Room placement (GAP-065)`: gap 49 != expected 0.** 1823 legacy rooms have
   a non-NULL `PlacementId`; only 1774 loaded with a non-empty `placement_note`.
   GAP-065's `expected_gap=0` was never validated against the live dump — the 49
   are likely `VillaRoomsPlacement` rows with a blank/whitespace `Name`
   (possible real fidelity loss, not just miscalibration). **→ GAP-065 follow-up:
   confirm whether the 49 carry recoverable placement text; recalibrate or fix.**
2. **`PropertyFinance (GAP-070)`: gap 1235 != expected 1236** (off by one). Stale
   estimate from before the live dump. **→ GAP-070 follow-up: recalibrate.**

### Test-infra note (pre-existing, surfaced by this branch's test count)

3 `seeding/tests/test_dashboard_activity.py` tests fail ONLY under the full
parallel suite (green in isolation, green running all of `seeding/`, green on
main's full suite). Cause: `transaction=True` + `--reuse-db` + timing-based
`-n auto` `load` distribution — a non-restoring `transaction=True` test that
co-locates on a worker before a dashboard test starves `seed_dev` of
migration-seeded reference data, so its `>= N today-activity` thresholds miss.
GAP-073's 36 new tests are all rollback-isolated (they don't contaminate); they
only shift the scheduler so the latent collision surfaces. **→ test-infra
follow-up: harden the dashboard tests (serialized_rollback / re-seed reference
data) or pin them to `loadscope`.**

## Run 3 — 2026-09-10 (GAP-107 cutover-fidelity leftovers, feat/gap-107)

Same 24-Apr-2025 dump (`res-db`), fresh `villacollective_legacy_dryrun`
migrated to the branch leaves (`pricing/0008_extra_legacy_id`, renumbered `0013` at the 2026-09-14 merge;
`properties/0008_propertyfinance_legacy_id`, renumbered `0009`). `loadlegacy --all` run twice
(idempotence), then `reconcile_legacy`.

### Census (legacy dump, `sqlcmd` one-liners; corrects the ticket's numbers)

The ticket quoted **137 extras / 71 regions / 57 active** — those came from the
git-tracked `DbScript.sql`, not the prod dump. Measured on the dump:

- **Extras** (`VillaSeasonRate WHERE DeletedAt IS NULL AND IsExTra = 1`):
  **96** across 18 villas. `CurrencyId = 0` on all, blank `Name` 0, `Price`
  NULL 0 (`= 0` on 3). `Commission` is the villa's commission-% snapshot (20 on
  86, 15 on 5, 0 on 5), `TaxAmount` 0 on all. `PriceType` 20 (gross) on 87,
  10 (net) on 9 — 7 of the net rows sit on deleted villas; the 2 live net rows
  (5238, 5341) have `Price = 0`, so **porting `Price` verbatim under-quotes no
  live extra**. `DeletedBy`-only deletions: 0.
- **Regions**: **64** total, 0 blank names, 0 orphans; 12 own-deleted
  (`DeletedBy`-only 0), 13 under deleted countries, 0 under live
  `IsActive = 0` countries → **42 active / 22 retired**.
- **Countries**: 23 rows; **6 live + active** (GR, IT, FR, MA, ES, KE — only
  GR carries `ShortName1`, the rest resolve by name); 17 deleted, 10 of them
  still `IsActive = 1`, including **United Kingdom (6)**, New Zealand (10),
  Australia and India (11 + 20). iso2 duplicates only involve deleted rows
  (France 3 live / 13 deleted; India 11 / 20 both deleted). England (24,
  iso2 `UK`, deleted) lands as a retired `UK` row for the §7 GB merge.
  *(2026-09-15, BUG-030 §6: superseded — `UK` now resolves to GB, row 24
  is skipped and aliased to GB in the loaders; §7 retired.)*
- **VillaFinance**: 1526 rows (`VillaId` is NOT NULL, so `VillaId IS NOT
  NULL` = every row). `VillaId = 0`: 1089 (413 `ParentId NULL` templates +
  676 parent-child overrides); `VillaId > 0`: 437 on 437 distinct villas — 146
  on deleted villas, 1 on villa 249 (the blank-name row PropertyLoader
  skips), **290 portable**. 311 override rows carry `VillaId > 0` and ARE the
  villa's only row — do not exclude on `ParentId`.

### Results

- **`loadlegacy --all` (first run) → exit 0, zero errors.** `country` 1
  created / 20 updated / 2 skipped (the France + India duplicate claims),
  `region` **64** created, `extra` **84** created / **12** skipped (11 on
  deleted villas + 1 on villa 249), `property_finance` **291** created (290
  stamped with `legacy_id` + the GAP-070 owner-contact fallback row:
  `finance_contact_defaults_applied applied=1 contact_only=0 skipped=2`).
- **Second `loadlegacy --all` → exit 0, idempotent.** `region` 0/64 updated,
  `extra` 0 created / 84 updated / 12 skipped, `property_finance` 0 created /
  290 updated, fallback `applied=0`; **no `extras_retired` event** (every
  ported extra re-appeared, so the full-run retirement pass touched nothing).
  Only `rate_rule` re-creates (3501) — its documented full-replace pattern.
- **`reconcile_legacy` — every GAP-107 check passes on live data:**
  `Country (active)` 6/6 gap 0; `Region` 64/64, `Region (imported)` 64/64,
  `Region (active)` 42/42 — all gap 0; `Extra` 96/84 gap 12 as first
  calibrated (11 on deleted villas — 97 Kapari bay ×4, 218 Villa K&K ×4, 108,
  411 ×2 — + 1 on villa 249), then re-shaped after review to mirror
  PropertyLoader's villa filter (`JOIN VillaMaster`, `DeletedAt IS NULL`,
  non-blank name) and count only active ported rows: **84/84 gap 0**,
  data-independent (re-run confirmed); `PropertyFinance` 1526/290 gap
  **1236 = expected** (1089 + 146 + 1, now itemised in the `_Check` comment —
  the run-2 "1235" was the fallback row inflating `loaded`, which the
  `legacy_id__isnull=False` scope removes). `RateBand` 7333/3528 gap 3805
  unchanged (the `IsExTra <> 1` split is disjoint from the new check).
- **Exit 1 on one PRE-EXISTING blocker:** `Room placement (GAP-065)` 1823/1774
  gap 49 != 0 — the run-2 Q-025 placeholder, unchanged and not touched by this
  branch (still needs the owner conversation).

### Side effects to surface at cutover (product-visible)

- Legacy deleted the United Kingdom row, so **GB loads retired**
  (`is_active=False`: readable, not offered in pickers), together with its
  region Orana; **IN, NZ and AU** retire the same way. **6 migrated properties
  sit in retired regions**, 0 in retired countries — they stay reachable, but
  the region no longer appears in the quote-builder geo pickers.
- The 84 ported extras are **opt-in** (`is_mandatory=False`); until GAP-111
  wires `opt_in_extras` into the quote builder they are catalogue + Zoho
  `extras[]` visibility only. Run `zoho_backfill --kinds villa` after the load
  so the villa payloads carry them.

## Run 4 — 2026-09-14 (BUG-028 money-path loaders, feat/bug-028)

Same 24-Apr-2025 dump (`res-db`), fresh `villacollective_bug028` migrated to
the branch leaves (post-GAP-110 `main`). `loadlegacy --all` run twice
(idempotence), then `reconcile_legacy`. **`reference_date` = 2026-09-14**
(the load day — `PropertyFinanceLoader`'s D7 rate-row window).

### Pre-flight (legacy dump)

- Every `IsDefault*` column the queries select exists on the dump
  (`VillaFinance.IsDefaultCommission/Paysched/SecDep`; `VillaMaster.IsDefaultSetting{CurrencyId,ChangeoverDayId,MinNightsRental,CheckInTime,CheckOutTime,BookingreqPreApp}`)
  — none are in the checked-in `DbScript.sql` DDL. Values: 0 / 1, plus NULL
  on 4 `VillaMaster` rows (read as unset).
- CPD row (`VillaConfigPropertyDefault`): `CurrencyId=3`,
  `CommissionType=10` / `CommissionAmount=20.00`, `ChangeOverDay=-1`,
  `MinimumNightsRental=7`, `IsBookingsRequirePreApproval=0`,
  `CheckinTime=16:30`, `CheckOutTime=10:30`, deposit 10 / 30.00 / 56 days,
  interim 10 / 20.00 / not required / 28 days, security deposit required /
  10 / 10.00 / refunded after 14 days.
- `VillaCurrency`: GBP 1, EUR **2 (deleted 2023-10-21)**, EUR **3 (live)**,
  USD 6; HTFG 4 / RUPEE 5 / RS 7 deleted.

### Results

- **`loadlegacy --all` (first run) → exit 0, zero errors.** `currency` 3
  created / 4 skipped; `rate_rule` **2829** created (was 3501);
  `property_finance` 291 created; `finance_rate_rows_mixed`
  `villas_with_rate_rows=9 mixed_count=0` (only 9 villas have rate rows
  ending on/after 2026-09-14 on a 2025 dump).
- **Second run → exit 0, idempotent.** Every loader 0 created except
  `rate_rule` (2829, its documented full replace); `property_finance`
  0 created / 290 updated.
- **Fallback villas** (`finance_contact_defaults_applied`): run 1
  `applied=1 contact_only=0 skipped=2`. Villas 464 / 466 (no owner) had no
  finance row at all — legacy reads a missing `VillaFinance` row as an
  all-zero model and fills it from the CPD, so the loader now resolves them
  from an empty row (BUG-028 U8a). Re-run of `property_finance`:
  `cpd_only=2`; all three fallback rows carry 20 % / 30 % / 10 % types.
- **Acceptance (psql, 293 imported villas):** calculation types non-NULL on
  291/291 finance rows (incl. the fallback rows); commission `percent 20.00`
  on 291/291; settings currency EUR (`legacy_id=3`) on 293/293 (every
  imported villa has a settings row — the ticket's 293 is right; 294 live
  `VillaMaster` rows less blank-name villa 249); min nights 7 on 292, 14 on 1;
  changeover `any` 36 (= 25 flagged 0 + 2 flagged −1 + 5 unflagged −1 + 4
  NULL-flag −1), `sun` 11 (unflagged 0, genuine Sundays); check-in/out
  16:30/10:30 on 246; pre-approval False everywhere (CPD 0); `Currency`
  EUR/GBP/USD active with legacy ids 3/1/6; rate plans EUR 225 / GBP 32 /
  USD 9; imported bands priced ≤ 0 non-POA: 0; unapproved: 0; 470 bands carry
  the `Unapproved in legacy (IsApprove=0)` marker. Unflagged security-deposit
  rows keep their own days due (72 × 7 days) — legacy keeps an own value
  `> 0`.
- **`reconcile_legacy`**: every BUG-028 check OK — `Currency (active)` 3/3,
  `Currency EUR legacy_id (live row)` 3/3, `PropertyFinance NULL calculation
  type` 0, `PropertySettings without currency` 0, `RateBand non-POA priced
  <= 0` 0, `RateBand unapproved imported` 0. **`RateBand` recalibrated 3805 →
  4492** (legacy 7333, loaded 2841), replayed through the loader pipeline
  with zero residual: 1154 outside the loader query + 108 occupancy parents
  replaced + 3099 priceless (792 newly: Price-only / 0.00) + 9 plan-less +
  106 capacity-emptied fallbacks + 136 shadowed − 108 fallbacks added − 12
  `#seg` fragments. Itemisation pinned on the `_Check`.
- **Exit 1 on three PRE-EXISTING blockers, none from this branch:**
  `Room placement (GAP-065)` 49 (unchanged since run 2), and villa **249**
  on both GAP-110 checks — `RatePlan (villas with a loaded regime)` 261/260
  gap 1 and night parity 64 legacy nights / 0 loaded. 249 is the blank-name
  `VillaMaster` row `PropertyLoader` skips (the `Property` gap of 1); both
  legacy queries join `VillaMaster` without the name filter. Left to GAP-108
  item 5 (pin or mirror the filter).

### D7 at the dump's own date (read-only replay, `reference_date` 2025-04-24)

230 villas have current priced non-POA rate rows; 197 carry a commission
majority, 1 a tax majority. 191 flagged-or-zero villas would take the
majority: `10 / 20.00` 182, `10 / 15.00` 8, `10 / 17.00` 3, `10 / 10.00` 1,
`10 / 16.67` 1, plus two suspect rows — `20 / 20.00` (a fixed EUR 20) and
`20 / 15000.00`. 11 villas are mixed (logged): 5, 11, 50, 51, 59, 164, 165,
168, 173, 245, 416. Only 4 villas have both an own explicit commission and
rate-row commission; 3 of those differ (460, 461, 465), only in the type:
own `0 / 20` (blank type, which the CPD fills to percent) vs rate rows
`10 / 20.00` — the same 20 %. Owner decision 2026-09-15: the majority beats
the own value, as legacy's quote does (rate row first,
`quote_price_calc-query.sql:96-146`). No villa's own tax is set, so tax
moves nothing. Strict legacy — a 0 rate-row commission also winning — was
rejected: 33 villas have only 0-commission current rows and would drop from
20 % to 0 %. Re-measure on the cutover dump with `reference_date` = the load
day.

### Side effects to surface at cutover (product-visible)

- 672 fewer imported bands: Price-only and 0.00 rows legacy could never
  quote no longer land as priced bands; seasons left with no quotable row
  lose their plan.
- Imported bands are all approved; 470 carry the legacy-unapproved marker
  in notes for staff review.
- Commission on all 291 finance rows is now 20 % (was NULL type / 0 on 68).

## Run 5 — 2026-09-15/16 (GAP-108 registry + reconcile + runbook, feat/gap-108)

**First run against `ResProd`** — the 13-Aug-2026 production database restored
from `ResSystem/NewResSystem_2026Aug13.bak` (545 `VillaMaster` rows, 73 tables).
The 24-Apr-2025 dump every earlier run used is gone, so **no figure from runs
1–4 carries over**: the gaps below were all re-derived here. Fresh
`villacollective_gap108b` / `c` / `d`, each migrated then loaded exactly once
(`loadlegacy --all` is a one-shot, BUG-029).

### Registry: 34 → 31 loaders

`BookingLoader`, `PaymentLoader` and `BookingChargeItemLoader` are
**unregistered** (GAP-089/GAP-108): historic bookings arrive from the Past
Bookers sheet (`import_past_bookers`), not `VillaBooking`. The modules and their
tests stay as the legacy-schema record, and three inverted checks —
`Booking` / `Payment` / `BookingChargeItem with legacy_id (must be 0)` — assert
that no row carrying a `legacy_id` ever lands in those tables.

### Results

- **`loadlegacy --all` → exit 0, all 31 loaders 0 errors.** Wall time
  **~7 minutes** (416.9 s measured; 6m16s and 6m56s on the two later loads) —
  the "~2 minutes" quoted before GAP-108 was the much smaller 24-Apr dump.
- **The run rebuilds the pricing summaries itself**, synchronously after the
  loaders and the sequence sync: `Rebuilt 359 pricing summaries.`
  (`loadlegacy.py:112-122`, crash-isolated into the report as a
  `<rebuild crashed>` row). `rebuild_summaries` is the manual recovery path,
  not a step anyone has to remember.
- **No Celery worker needed.** `LLEN celery` is **0 before and after** the
  load: `BaseLoader.load()` wraps every row loop in `suppress_zoho_push()` +
  `suppress_summary_rebuild()`, so nothing is enqueued in the first place.
  (The ticket's "4 086 / 7 577 messages per load" was measured before that
  suppression landed.)
- **`AuditLog` after one load: 72 009 rows** — propertyimage 18 232,
  propertyfeature 13 359, quotationline 7 556, rateband 6 633, person 6 252,
  rateperiod 6 222, enquiry 5 081. Expected, and the bulk of the load's write
  volume; size the transaction log for it.
- **`reconcile_legacy --integrations` → exit 0.** Re-measured on
  `villacollective_gap108d` at HEAD on 2026-09-16: **54/54 row-count rows OK**,
  the `RatePeriod` night-parity section reports **0 villas** ("every villa's
  loaded periods cover exactly its legacy nights"), and all four Zoho
  continuity rows OK. Running `createsuperuser --noinput` first changes
  nothing — the loaded side now defaults to `legacy_id IS NOT NULL`, so staff
  rows and the sheet imports cannot move a gap.
- **15 of the 54 checks are non-zero**, each itemised to zero residual in its
  `_Check` comment and mirrored in `CUTOVER.md` §5: `Country (legacy)` −225,
  `Currency` 4, `PersonEmail` 2, `PersonPhone` 8, `CollectionMembership` 9,
  `Room` 321, `Room placement (GAP-065)` 61, `PropertyImage` 839,
  `PropertyNearbyPlace` 78, `RateBand` 462, `PropertyContactAssignment` 6,
  `Person (client)` 184, `PropertyFinance` 1239, `QuotationLine` 345,
  `GuestPreference` 201.
- **Q-025 / `Room placement` closed.** The gap run 2 raised as a blocker and
  runs 3–4 carried forward is now pinned at 61 with its derivation (rooms on
  unloaded villas, plus dangling `PlacementId`s whose
  `VillaRoomsPlacement.Name` is blank), not a placeholder.
- **`RateBand` re-derived, not re-nudged.** The check's *legacy query* was
  wrong: it counted a 39 868-row universe that was never the loader's input, so
  both numbers ever documented against it (3805, then 4492) are dead. Real
  universe 7 095, loaded 6 633, gap **462**.
- **Zoho continuity:** `VillaMaster` gap 1 (the Temenos pair, decision 1
  above), `VillaEnquire` gap 1, `VillaQuotationMaster` gap 0, and
  `VillaContact` **0 external ids on ResProd** — there is no contact
  continuity to capture at all, so every contact push starts fresh.

### Side effects to surface at cutover (product-visible)

- `VillaAvailability (future days)` is gap 0, but **both sides move with
  "today"**: the loader filters at load time and the check queries `GETDATE()`
  at reconcile time, so load and reconcile in one sitting or a day crossing
  shows a spurious negative gap. `PropertyFinanceLoader.reference_date` (the
  load day) has the same property.
- 178 distinct (villa, collection) pairs exist only as `IsActive IS NULL`
  rows and do not load — legacy's own `isnull(IsActive,0) = 1` convention
  hides them from the legacy UI too. If a collection looks thin after
  cutover, that is why; reinstating them is a product decision.
