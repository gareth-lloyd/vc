# Migration Acceptance Standards

How we judge that a full legacy → Postgres migration has **truly succeeded in
capturing all information**. `CUTOVER.md` is the *ops runbook* (how to run the
cutover); this document is the *definition of done* (how to know it worked).
A migration is accepted only when **every standard below holds**, or a failure
is recorded as an accepted loss with a written justification.

The standards are ordered by strength: each level catches failures the
previous one cannot.

## S1 — Coverage: every legacy table is accounted for

Every table in the legacy production database (`ResProd`, the 13-Aug-2026
snapshot — 73 tables) must be in exactly one of these buckets, recorded in the
coverage matrix (`COVERAGE.md`):

1. **Loaded** — a registered loader reads it (as primary source or join).
2. **Deliberately dropped** — with a written justification (junk, dead
   feature, no schema home *and* no information content worth preserving).
3. **Deferred** — real information we are knowingly not loading *yet*, where a
   **named open ticket owns the decision** (e.g. `VillaArchiveBookings` →
   GAP-113). A deferral without a ticket id is a blocker, not a deferral:
   the ticket is the whole difference between "decided later" and "forgotten".
4. **Blocker** — anything not in buckets 1–3. Unclassified tables fail
   acceptance; "we forgot it existed" is the failure mode this standard
   exists to catch.

The matrix is regenerated against the live dump at cutover
(`SELECT name FROM sys.tables`) — not against our memory of the schema — so
a table added to legacy after this document was written surfaces as a
blocker, not a silent omission.

## S2 — Row-count reconciliation: `reconcile_legacy` exits zero

`reconcile_legacy` compares filtered legacy counts to loaded counts per
check, enforcing calibrated `expected_gap` values. Standards:

- The command **exits zero** on the final cutover dump. Any unexplained gap
  is a blocker.
- **No placeholder gaps.** Every `expected_gap` in `_CHECKS` has been
  calibrated against a recent dump, with the gap's composition *itemised* to
  zero residual (e.g. `PropertyFinance` 1239 = 413 contact-default templates
  + 676 parent-child overrides + 150 rows on villas the property loader
  excludes), not just asserted as a number. A gap we can't decompose is a gap
  we don't understand.
- **Every loader has a check.** A loader without a reconcile row can
  silently load zero rows; the `Organisation (agency)` check exists for
  exactly this reason. All 31 registered loaders carry one bar
  `syncrecord_zoho`, whose row lives in the `--integrations` section.
  Loaders whose output is not 1:1 with a legacy table (expansions,
  synthesised rows) need a check written in terms of the loader's own
  arithmetic (e.g. `RateBand`: surviving flattener sources + synthetic
  occupancy fallbacks − multi-cell fragments). The converse holds too — a
  **retired** loader gets an inverted check: `Booking` / `Payment` /
  `BookingChargeItem with legacy_id (must be 0)` pin the three loaders
  GAP-089/GAP-108 unregistered.
- Per-loader `errors` and `skipped` counts from `loadlegacy --all` are zero
  or itemised-and-accepted.

## S3 — Field-level fidelity: values survive, not just rows

Row counts prove presence, not correctness. For each **key data structure**
(see the translation-pattern inventory in `COVERAGE.md`), a field-level
sample check must pass against the live dump:

- **Deterministic spot checks**: for a random sample of N rows per table
  (N ≥ 50, seeded so re-runs are comparable), compare each mapped column
  legacy → new through the documented transform. Zero unexplained
  mismatches.
- **Aggregate invariants** (catch what sampling misses):
  - Money: per-currency sums of quotation-line amounts, rate-band prices and
    the per-villa finance figures
    (`Σ legacy = Σ loaded + Σ itemised drops`). Bookings, payments and charge
    items left the migration with GAP-089/GAP-108 — they arrive from the Past
    Bookers sheet (`import_past_bookers`), so they carry no legacy money for
    this standard to reconcile. The amounts `import_archive_stays` (GAP-113)
    copies onto `PastStay` from `VillaArchiveBookings` are recorded as
    staff keyed them, with no currency when legacy had none. They are not
    reconciled as money: `reconcile_legacy` checks only that every archive
    stay has landed (nothing left to enrich or create), not the amounts.
  - Dates: min/max of arrival/departure, season spans per property.
  - Text: non-null/non-blank counts for descriptions, notes, references
    (catches encoding truncation and over-eager stripping).
- **Reference continuity**: every imported quotation keeps its exact legacy
  number (`QVC{n}` — no bookings are imported, so there is no `VC{n}` side);
  enquiry references keep their legacy shape; the quotation sequence is
  fast-forwarded past the imported high-water mark (`sync_quotation_sequence`,
  whose line `loadlegacy` prints) so the first organic row cannot collide.

## S4 — Relational integrity: the graph survives

- **No orphans**: every loaded child resolves its parent (quotation line →
  quotation, room → property, rate band → rate plan, …). Sentinel fallbacks
  (`unknown_country`, `unknown_client`, …) are counted and itemised — a
  sentinel count that jumps between dry runs is a regression even when row
  counts hold.
- **External-ID continuity** (Zoho): `reconcile_legacy --integrations` gap is
  zero — every *loaded* row that carried a legacy `ZohoId` has a
  `SyncRecord`. This is unrecoverable after legacy decommission, so it blocks.
- **Cross-table consistency**: denormalised pointers and required satellites
  agree with their source tables — mechanised as `SELECT 0` invariants in
  `_CHECKS` (e.g. `PropertySettings without currency`,
  `Person (owner/agent) primary email count != 1`), one row per loaded
  `Property` for location / capacity / settings.

## S5 — Behavioural parity: the numbers legacy showed are reproducible

The strongest form of evidence: the new system, asked the same question as
legacy, gives the same answer (or a documented, deliberate delta).

- **Booking totals — no longer a migration standard.** `loadlegacy` imports
  no bookings, payments or charge items (GAP-089/GAP-108 unregistered those
  three loaders; the `… with legacy_id (must be 0)` invariants pin it), so
  there is no legacy booking total for the new system to reproduce. Parity
  for what *is* imported is the quote sample below.
- **Quote parity sample**: for a sample of (property, week, party-size)
  tuples that legacy priced, the new engine returns the same weekly rate —
  except where the rate-overlap resolution deliberately changed an
  arbitrary-winner case (those seasons are enumerable from the
  `rate_rule_overlaps_resolved` counters and must be listed, not waved at).
- **Deliberate deltas are enumerated**: every place we chose to diverge from
  legacy (blind cross-currency sums, arbitrary overlap winners, role remap)
  has (a) a doc reference, (b) a count of affected rows on the live dump,
  (c) a statement of who accepted it.

## S6 — Process properties: the run itself is trustworthy

- **One-shot guard** (BUG-029): the load is a one-shot into a fresh DB, so a
  second `loadlegacy --all` on the loaded DB must exit non-zero with the
  "fresh, migrated database" message and write nothing (no loader runs, no
  sequence sync). Rollback-and-retry is drop / recreate / `migrate` / reload.
- **Determinism**: the same dump loaded into two fresh DBs gives the same
  result — every order-dependent outcome (duplicate resolution, hero image,
  sentinel `legacy_id`) is pinned by an `ORDER BY` or explicit tie-break —
  covered by `tests/test_loader_ordering.py` and the loaders' own suites.
- **Order safety**: `migrate` before `loadlegacy` (load-bearing per
  GAP-045 D5-4c); registry order satisfies every FK dependency — verified by
  the fresh-DB dry run, not by inspection alone.
- **Signal discipline**: `BaseLoader.load()` wraps every loader's row loop in
  `suppress_zoho_push()` + `suppress_summary_rebuild()` (`base.py:84`), so a
  load pushes nothing to Zoho and enqueues no Celery task — `LLEN celery`
  reads 0 both before *and* after the run, and no worker is needed.
  `loadlegacy` then rebuilds the pricing summaries itself in one synchronous
  pass (`Rebuilt N pricing summaries.`, crash-isolated into the summary
  table); `rebuild_summaries` is the manual recovery path, not a required
  step. Detail in `CUTOVER.md` §4a. Verified by a test, not just code review.
- **No leakage**: nothing in the load mints the synthesised `legacy_id`
  prefix `booking-` any more — only the now-unregistered `BookingLoader` did —
  so the `.real()` manager method every quotation queryset goes through
  (`SYNTHETIC_LEGACY_PREFIX`, `reservations/models/quotation.py`; used by
  `QuotationViewSet`) should be a no-op. The guard stays regardless. A non-empty
  `Quotation.objects.filter(legacy_id__startswith="booking-")` means a booking
  loader ran; the smoke test is in `CUTOVER.md` §9.

## S7 — Recoverability: nothing time-critical is lost

Some data exists *only* in the legacy DB and dies with it (`CUTOVER.md` §10,
retire the legacy container). Before decommission:

- Zoho external IDs captured (S4).
- The final dump is archived to the retention store **before** the container
  is destroyed.
- Anything in the "deliberately dropped" bucket that is *information-bearing*
  (vs junk) is either exportable from the archived dump on demand, or the
  drop justification says why we will never need it.

## Verdict procedure

Run order at each dry run / the real cutover:

1. `loadlegacy --all` (~7 min on ResProd) → all 31 loaders `0` in the errors
   column, plus the `Rebuilt N pricing summaries.` line (S2, S6)
2. `reconcile_legacy` + `--integrations` → exit zero (S2, S4)
3. Coverage matrix regeneration against `sys.tables` (S1)
4. Fidelity + invariant scripts (S3, S4, S5)
5. Second `loadlegacy --all` on the loaded DB → refused, exit non-zero (S6)

Record the results per standard (pass / accepted-loss / blocker) in the
dry-run log. **Accepted-loss requires**: what is lost, how many rows, why
it's acceptable, who accepted it, and where the data remains recoverable
(usually the archived dump).
