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

## Environment

- Legacy: `res-db` container (Azure SQL Edge), DB `NewResSystem` from the
  24-Apr-2025 prod dump, survived in the `ressystem_res-db-data` volume.
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

5. **IsDefault* resolution never implemented.** Legacy
   (`PropertyService2.cs:668-688`): when a villa's `IsDefault*` flag is set,
   the `VillaConfigPropertyDefault` value OVERRIDES the stored column.
   Measured on live villas: min_nights loads 1 instead of effective 7 for
   **197 villas**; commission loads 0% instead of effective **20%** for 68
   finance rows (money!); currency loads None instead of EUR for 91 villas.
   Fix in PropertyLoader/finance loaders (read the single CPD row as
   constants), then the table itself is droppable.
6. **`_COMMISSION_TYPE_MAP = {1: PERCENT, 2: FIXED}`** but legacy
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
**36/36 rows OK**; second load creates rows ONLY in the two by-design
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
