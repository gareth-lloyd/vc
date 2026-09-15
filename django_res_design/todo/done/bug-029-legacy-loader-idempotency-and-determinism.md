# BUG-029 — Legacy loader: re-runs strip primary contacts, `--since` crashes half the loaders, and several outcomes depend on row order

> **✅ RESOLVED (2026-09-15)** — shipped on `feat/bug-029` (U1 a2d7bbc7, U2 d2f67997, U3 c9fa5c88, U4 4a56de05, U5 6fb21f05, U6 docs). **User
> decision 2026-09-15: `loadlegacy` is a one-shot cutover** into a fresh,
> migrated DB; in-place second runs are unsupported, and a late write or failed
> run means drop, recreate, `migrate` and reload from a newer dump.
> U1 `merge_country --dry-run` rolls back via `transaction.set_rollback(True)`
> and exits 0. U2 `--since` retired entirely (flag, loader arg, `_apply_since`,
> per-loader overrides); the extras retire sweep always runs and
> `property_defaults` no longer skips. U3 per-row savepoints in
> `availability_block` (`avail-<pid>-<start>`) and `syncrecord_zoho`
> (`<table>:<Id>`); a `sync_quotation_sequence` failure is a summary row, the
> summary still prints and the exit is non-zero. U4 deterministic ordering
> (images, membership, country, region, declarative base, contact-default
> finance, nearby-place subselect); the country sentinel keeps `__unknown__`
> and ISO-less junk rows are skipped + logged. U5 `loadlegacy --all` refuses
> a DB whose Country/Currency/Property already holds a `legacy_id` (no
> `--force`; named loaders stay unguarded as a debugging aid).
> **Won't-fix (one-shot makes them moot):** §1 primary e-mail/phone demotion on
> re-run, §5 the two-run idempotency test, §6 the stale `villa:` regime-plan
> sweep (and BUG-028's in-place leftovers, e.g. stale `season:<ID>:svc`).
> **Deviations from the proposed fix:** availability recency is
> `(COALESCE(UpdatedAt, CreatedAt), Id)` with the blocking-status filter moved
> after the dedupe (not `Id DESC` — legacy updates rows in place), mirrored by
> `reconcile_legacy` with `ROW_NUMBER()`; membership uses `ORDER BY
> VillaMasterId, VillaCollectionId, ISNULL(VillaOrder, 2147483647), Id` (lowest
> order wins, NULL last) rather than `MIN()`; the one-shot
> guard (U5) was added; CUTOVER §6 says "fresh reload", not "re-run
> `loadlegacy --all`".

- **Severity:** 🔴 Bug (a second `loadlegacy --all` — the documented
  rollback / late-write path — silently damages data; the count-only
  idempotency check in `DRYRUN_LOG.md` cannot see it).
- **Source:** 2026-09-11 legacy-loader audit; verified by running
  `loadlegacy --all` three times on the scratch DB `villacollective_loaderaudit`.
- **Files touched:**
  - `django_res/data_migration/loaders/people.py:116-117, 142-143`
    (primary demotion), `:140-141` (phone string).
  - `django_res/data_migration/base.py:81-97` (`_apply_since`),
    `management/commands/loadlegacy.py` (`--since` flag, `:82`
    `sync_quotation_sequence` outside the isolation).
  - `django_res/data_migration/declarative.py:31-33` (no `ORDER BY`),
    `loaders/lookups.py:75-77` (currency keep-first),
    `loaders/property_children.py:139-151` (hero choice),
    `loaders/properties.py:332-340` (membership keep-first),
    `loaders/country.py:70-80` (sentinel `legacy_id` overwrite),
    `loaders/availability.py:114-119` (day dedupe).
  - `django_res/data_migration/loaders/integrations.py:158-160`,
    `loaders/availability.py:196-250` (no per-row savepoint).
  - `management/commands/merge_country.py:86` (dry-run exits 1).
  - `django_res/data_migration/CUTOVER.md` §1, §6; `ACCEPTANCE.md` S6;
    `DRYRUN_LOG.md`.
  - Tests: `tests/test_country_loader.py:43-60` (pins the sentinel
    overwrite), `tests/test_availability_loader.py:92` (pins order-agnostic
    keep-first); no two-run test exists anywhere.

## Problem

### 1. Primary email/phone flips to False on every re-run

`ContactEmailLoader` and `ContactPhoneLoader` demote a row when the contact
"already has a primary" — but the check does not exclude the row's own
`legacy_id`, so on run 2 the row sees itself and writes
`is_primary=False, label=OTHER`. Scratch DB after three loads: **0 of 222**
legacy e-mails and **1 of 165** phones are primary. Every owner/agent loses
their primary contact on the first re-run. `PropertyContactAssignmentLoader`
(`reservations.py:99-108`) already does the exclusion correctly.

### 2. `--since` delta mode crashes 18 of 33 loaders and misses inserts anyway

`_apply_since` appends `UpdatedAt > …` to every `BaseLoader` query. Sixteen
source tables have no `UpdatedAt` column (country, region, currency,
nearby_place_type, feature_category, feature, contact, collection,
collection_membership, room, property_image, property_finance,
quotation_line, guest_preference_type, guest_preference, payment →
`Invalid column name 'UpdatedAt'`), and the `" where " in query.lower()`
heuristic is fooled by a sub-select WHERE (`nearby_place`) and a GROUP BY
(`property_feature`) → `Incorrect syntax`. The run exits 1. CUTOVER §6 says
those loaders "silently ignore the flag"; ACCEPTANCE S6 says they "warn
loudly". Neither is true.

Even for the loaders that work, 436/451 `VillaEnquire.UpdatedAt` are NULL
(inserts never set it; 10/19 quotations likewise), so a delta run skips every
enquiry created after the freeze — on the one legacy path that stays live.

**Decision 2026-09-11: retire `--since`.** The load is a one-shot; the
late-write fix is a full re-run, which every loader already supports
(`rate_rule` full-replaces, everything else upserts). Removing the flag is
simpler than an opt-in `since_column` + `COALESCE(UpdatedAt, CreatedAt)` +
placeholder rewrite that would still need its own SQL-pinning tests.

*GAP-107 (merged 2026-09-14) gave `CountryLoader` and `RegionLoader` their
own `_apply_since` override (`legacy_changed_since_sql()` in
`loaders/_util.py`, on legacy's real `CreatedAt`/`UpdateAt`/`DeletedAt`), so
those two no longer crash. Delete both overrides and the helper along with
the flag. (This replaces GAP-107's planned `--since` follow-up ticket.)*

### 3. Order-dependent outcomes with no `ORDER BY`

- **Currency keep-first** — the live EUR loses to its deleted twin
  (BUG-028 §3 owns the fix; listed here because it is the same class).
- **Country iso2 collisions** — 13 "France" vs 3, 20 "India" vs 11; both
  losers are deleted today, so harmless, but undefined.
- **Image hero** — 9 live villas (3, 15, 81, 118, 141 ×3, 177, 207, 219, 313)
  have 2–3 active `IsHero` images, all `SortOrder=0`; which stays HERO
  depends on row order.
- **Collection membership** — "keep first seen" on the 3 duplicate pairs
  (villa 3/coll 13 has `VillaOrder` 6 vs 13).
- **Country sentinel `legacy_id`** — overwritten "last unknown wins" by each
  of the 10 junk rows (ends as `"23"`, each hit counted as `updated`), so
  `merge_country --from-legacy 12` cannot find it. The test pins this.
- **Availability duplicate (property, day) rows** — 380 pairs in the dump,
  **208 with differing statuses** (e.g. villa 3 / 2025-05-23: status 50 at
  09:16, status 60 at 09:27). Keep-first over `ORDER BY PropertyId,
  AvailableDate` with no tiebreak resolves to an arbitrary, probably stale,
  status. The test pins keep-first without ordering.

### 4. Crash isolation has holes

`SyncRecordZohoLoader` and `AvailabilityBlockLoader` have no per-row
savepoint, so one write-time exception aborts the whole loader as
`<loader crashed>` with no row id. `sync_quotation_sequence()` sits outside
the isolation in `loadlegacy.py:82`; if it raises, no summary prints and
every report is lost. `merge_country --dry-run` raises `CommandError` to
roll back, so a successful preview exits 1 in a script
(`recompute_derived_features.py:59-61` shows the `set_rollback` pattern).

### 5. Nothing tests a second run

`DRYRUN_LOG.md`'s "byte-identical second reconcile" is a row-count
comparison. §1 passed it three times.

### 6. A re-resolved villa leaves a stale regime plan behind

Since GAP-110 the `rate_plan` loader keys plans `villa:<VillaId>:<CODE>`
and its sweep only deletes pre-regroup (non-`villa:`) loader plans. If a
villa's currency re-resolves on a later run (e.g. BUG-028's currency fix
turns EUR into GBP) or it loses all its priced rows, the old
`villa:<id>:EUR` plan is not swept: the band full-replace removes its
periods and it survives as an **active, periodless** plan. Harmless to
pricing (period-first selection skips it) but it shows in the workbench
picker and occupies the `(property, currency, GROSS)` active slot, so staff
can't create a plan in that regime. `CUTOVER.md` §5 item 6 records it as a
hand-cleanup leftover.

## Proposed fix

1. `.exclude(legacy_id=str(row["Id"]))` in both demotion checks, mirroring
   `PropertyContactAssignmentLoader`.
2. Remove `--since`, `_apply_since`, the `-- /*SINCE*/` docstring promise and
   the per-loader "ignores --since" warnings; rewrite CUTOVER §1 ("capture
   the freeze timestamp") and §6 to "re-run `loadlegacy --all`"; fix
   ACCEPTANCE S6.
3. Add an explicit `ORDER BY` to every query whose keep-first matters:
   `ORDER BY i.VillaId, i.Id` for images; `MIN(Id)` / `MIN(VillaOrder)` in
   SQL for memberships (like the feature loader); `ORDER BY PropertyId,
   AvailableDate, Id DESC` for availability so keep-first = latest edit
   (invert the pinned test); keep the country sentinel's `legacy_id` as
   `__unknown__` and log the skipped ids instead.
4. Per-row `transaction.atomic()` + `(legacy_id, repr(exc))` in the two
   loaders that lack it; move `sync_quotation_sequence()` inside the
   isolation; `transaction.set_rollback(True)` for the dry-run.
5. **A two-run idempotency test** on a small real-shaped fixture set (one
   contact with e-mail + phone, one villa with two hero images, one
   duplicate availability day): run every loader twice and assert
   field-level equality, not counts. This is the regression net for the
   whole package.
6. At the end of `RatePlanLoader`, delete `villa:`-keyed plans whose
   `legacy_id` was not produced this run and which own no non-legacy
   (staff) periods; deactivate the rest and log them. Drop the "known
   leftover" note from `CUTOVER.md` §5 item 6. Covered by the two-run test
   with a villa whose currency changes between runs.

## Acceptance

- Scratch-DB double run: `PersonEmail`/`PersonPhone` primary counts identical
  after run 2; hero image identical; availability status = latest row.
- `loadlegacy --help` shows no `--since`; CUTOVER/ACCEPTANCE/DRYRUN_LOG
  mention no delta mode.
- The two-run test is in CI and fails if any loader's second pass changes a
  field.
- A villa whose resolved currency changes between runs ends with exactly
  one active `villa:` plan; no periodless loader plan survives.
- Quality gate green.

## Dependencies

- **BUG-028** should land first (its currency fix removes the largest
  order-dependence; the two-run test is most useful against corrected
  output). **Landed 2026-09-14** — build the two-run test against it. Two
  in-place re-run leftovers it documents but does not fix: a season whose
  rows all became unquotable (Price-only / `0.00`) keeps its
  `season:<ID>:svc` inclusion service, and a regime plan left with no
  quotable rows is not removed. Its per-villa commission depends on
  `reference_date` (the load day), so a two-run test must pin that date.
- **GAP-108** carries the doc pass that references this ticket's `--since`
  removal.
