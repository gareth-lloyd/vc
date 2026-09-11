# GAP-108 — Legacy loader: unregister the dead booking loaders, make `reconcile_legacy` prove what it claims, and bring the runbook back to the code

- **Severity:** 🟠 Gap (cutover process). Backend `data_migration/` + docs.
- **Source:** 2026-09-11 legacy-loader audit; live `loadlegacy --all` +
  `reconcile_legacy` on scratch DB `villacollective_loaderaudit`
  (24-Apr-2025 dump). Absorbs GAP-107 §3 (the 1236 pin) and Q-025's
  `Room placement` placeholder, both now explained.
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
  234; villas 464/466 have no mapping → skipped). Fallback rows carry no
  marker, so pin the constant with this arithmetic.
- **Most checks count organic rows too** (`:100-114, 187, 240, 354-391`:
  User, Region, Currency, Collection, Feature, RatePlan, Quotation, Booking,
  Payment use a bare `count()`). A `createsuperuser` before reconcile turns
  User into a blocker; any staff-created row does the same. Three checks
  already scope to `legacy_id__isnull=False`.
- **No check at all** for `property_feature` (11 955 rows — BUG-030 §11 adds
  it), `property_defaults`, and the satellites PropertyLocation / Capacity /
  Settings / Description, RoomBeds, PropertyService, RatePeriod,
  BookingGuest. ACCEPTANCE S2 says every loader has a check.
- **Right numbers, wrong reasons**: CollectionMembership 308 ("duplicates";
  see BUG-030 §13), PropertyContactAssignment 1 ("composite legacy_id
  collapse"; all 335 are unique — it is the mapping on blank-name villa 249),
  GuestPreference 93 (BUG-030 §30), Currency 4 (3 junk + the *live* EUR,
  BUG-028 §3), Person (owner/agent) filters `DeletedAt IS NULL` while the
  loader loads deleted contacts INACTIVE (masked: 0 deleted in the dump),
  VillaAvailability narrative (property 133, 2026-07-25 → 08-22) aged out —
  today 0 = 0 trivially.
- **Count checks cannot see value regressions.** BUG-028's four defects and
  BUG-029's primary-flag flip all passed. BUG-028 adds the money invariants;
  this ticket adds the structural ones: primary-e-mail count equals loaded-
  e-mail count; zero active `Region`/`Country` rows whose legacy twin is
  deleted (GAP-107 §2); zero `Property.slug` containing `://`.

### 3. The runbook describes a loader that no longer exists

- COVERAGE `:7` "60 tables": the dump has 61 and all 61 are classified.
- CUTOVER §6 "loaders without `UpdatedAt` silently ignore `--since`": they
  crash (BUG-029 retires the flag; §1 and §6 need rewriting).
- CUTOVER §4 IsDefault list omits changeover day (27 villas) and says
  currency ×91 (188 — BUG-028 §2/§3); §4c mentions the `E-{Id:06d}` fallback
  that never fires and `/api/quotations` (actual `/api/v1/quotations`);
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
- ACCEPTANCE S6 "loaders that ignore `--since` warn loudly"; DRYRUN_LOG
  `:210` "36/36 rows" vs 33 checks today.
- COVERAGE claims `VillaConciergeServices` maps to TextChoices (no field
  exists — GAP-109) and that only "298 Sea View" has multiple categories
  (50/229 live features do).
- SMELL-021's "legacy has no NET/GROSS signal" is wrong (1 931 Net rows;
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
   placement 49 and PropertyFinance 1235 with their derivations; add the
   missing checks (a satellites check can be "one per loaded Property");
   rewrite the wrong reasons; add the structural value invariants.
3. Docs pass over CUTOVER / COVERAGE / ACCEPTANCE / DRYRUN_LOG / CLAUDE.md
   for every item in §3, plus the §4 runbook notes (pause worker, audit
   volume, real timings). Parameterise `drop-and-reseed.sh` on the dump
   filename.
4. Recount GAP-107 §2 and note that §3 closed here; note Q-025's placeholder
   closed here; note the Zoho contact fact on GAP-098.

## Acceptance

- `loadlegacy --all` runs 30 loaders; `Booking`/`Payment`/`BookingChargeItem`
  counts are 0 on a fresh load.
- `reconcile_legacy` exits 0 on the dump with no PLACEHOLDER markers left,
  every constant explained in its comment, a check for every registered
  loader, and the value invariants green.
- A `createsuperuser` before reconcile does not change the result.
- Every §3 line corrected; `grep -n "Guest.merge\|--since\|60 tables"` finds
  nothing stale.
- Quality gate green.

## Dependencies

- Sequence after **BUG-028 / BUG-029 / BUG-030** — they move most of the
  constants this ticket pins; do the pinning last on one dry-run.
- **GAP-107**: §3 closes here; §1 (extras) and §2 (deleted geo as inactive)
  stay there. **Q-025**: its reconcile residual closes here. **GAP-098**:
  Zoho contact note. **GAP-103**: still blocked on GAP-107 §2, not on this.
