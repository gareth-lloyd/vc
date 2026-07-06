# Migration Acceptance Standards

How we judge that a full legacy → Postgres migration has **truly succeeded in
capturing all information**. `CUTOVER.md` is the *ops runbook* (how to run the
cutover); this document is the *definition of done* (how to know it worked).
A migration is accepted only when **every standard below holds**, or a failure
is recorded as an accepted loss with a written justification.

The standards are ordered by strength: each level catches failures the
previous one cannot.

## S1 — Coverage: every legacy table is accounted for

Every table in the legacy `NewResSystem` database must be in exactly one of
these buckets, recorded in the coverage matrix (`COVERAGE.md`):

1. **Loaded** — a registered loader reads it (as primary source or join).
2. **Deliberately dropped** — with a written justification (junk, dead
   feature, no schema home *and* no information content worth preserving).
3. **Blocker** — anything not in buckets 1–2. Unclassified tables fail
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
  calibrated against a recent dump, with the gap's composition *itemised*
  (e.g. "1236 = 413 contact-default mirrors + 676 parent-child overrides"),
  not just asserted as a number. A gap we can't decompose is a gap we don't
  understand.
- **Every loader has a check.** A loader without a reconcile row can
  silently load zero rows; the `Organisation (agency)` check exists for
  exactly this reason. Loaders whose output is not 1:1 with a legacy table
  (expansions, synthesised rows) need a check written in terms of the
  loader's own arithmetic (e.g. parents + valid bands + gap fallbacks −
  drops).
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
  - Money: per-currency sums of booking `RentalPrice`, payment amounts,
    charge-item amounts (`Σ legacy = Σ loaded + Σ itemised drops/conversions`).
    FX-converted charge items are itemised, never lost in the aggregate.
  - Dates: min/max of arrival/departure, season spans per property.
  - Text: non-null/non-blank counts for descriptions, notes, references
    (catches encoding truncation and over-eager stripping).
- **Reference continuity**: every imported quotation/booking keeps its exact
  legacy number (`QVC{n}`/`VC{n}`); enquiry references keep their legacy
  shape; sequences are fast-forwarded past the imported high-water mark so
  the first organic row cannot collide.

## S4 — Relational integrity: the graph survives

- **No orphans**: every loaded child resolves its parent (booking → property,
  quotation line → quotation, charge item → booking, …). Sentinel fallbacks
  (`unknown_country`, `unknown_client`, …) are counted and itemised — a
  sentinel count that jumps between dry runs is a regression even when row
  counts hold.
- **External-ID continuity** (Zoho): `reconcile_legacy --integrations` gap is
  zero — every *loaded* row that carried a legacy `ZohoId` has a
  `SyncRecord`. This is unrecoverable after legacy decommission, so it blocks.
- **Cross-table consistency**: denormalised pointers agree with their source
  tables (e.g. `Booking.guest` ↔ LEAD `BookingGuest` row exists, 1:1).

## S5 — Behavioural parity: the numbers legacy showed are reproducible

The strongest form of evidence: the new system, asked the same question as
legacy, gives the same answer (or a documented, deliberate delta).

- **Booking totals**: for every imported booking, new
  `balance_due + Σ charge_items` equals legacy `RentalPrice + Σ details` —
  except the itemised FX-converted set, whose delta is per-row explainable.
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

- **Idempotency**: a second `loadlegacy --all` immediately after the first
  converges — reconcile output identical, no duplicate rows, full-replace
  loaders show clean purge-and-reload, `updated` not `created` for upsert
  loaders. (This is the property that makes rollback-and-retry safe.)
- **Order safety**: `migrate` before `loadlegacy` (load-bearing per
  GAP-045 D5-4c); registry order satisfies every FK dependency — verified by
  the fresh-DB dry run, not by inspection alone.
- **Delta correctness**: loaders that ignore `--since` (rate_rule,
  booking_charge_item, lookup tables without `UpdatedAt`) are enumerated and
  warn loudly; a `--since` pass on the dry-run dump does not corrupt a
  previously-full-loaded state.
- **Signal discipline**: side-effect signals that would rewrite imported
  financial data are suppressed for exactly the loader's row loop
  (`resync_on_booking_total_changed`), and reconnected after — verified by a
  test, not just code review.
- **No leakage**: synthesised rows (`legacy_id` prefix `booking-`) do not
  appear in public API list endpoints.

## S7 — Recoverability: nothing time-critical is lost

Some data exists *only* in the legacy DB and dies with it (step 10 of the
runbook). Before decommission:

- Zoho external IDs captured (S4).
- The final dump is archived to the retention store **before** the container
  is destroyed.
- Anything in the "deliberately dropped" bucket that is *information-bearing*
  (vs junk) is either exportable from the archived dump on demand, or the
  drop justification says why we will never need it.

## Verdict procedure

Run order at each dry run / the real cutover:

1. `loadlegacy --all` → per-loader errors/skips table (S2, S6)
2. `reconcile_legacy` + `--integrations` → exit zero (S2, S4)
3. Coverage matrix regeneration against `sys.tables` (S1)
4. Fidelity + invariant scripts (S3, S4, S5)
5. Second `loadlegacy --all` → convergence diff (S6)

Record the results per standard (pass / accepted-loss / blocker) in the
dry-run log. **Accepted-loss requires**: what is lost, how many rows, why
it's acceptable, who accepted it, and where the data remains recoverable
(usually the archived dump).
