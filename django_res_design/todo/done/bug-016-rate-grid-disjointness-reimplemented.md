> **✅ RESOLVED (2026-07-05)** — Problem: the (date × party)-disjoint / precedence / `#seg{n}` invariant
> was copy-derived in four producers (lazy projection + carryover + legacy loader + period backfill) that
> could — and did — disagree: a projected quote could price differently from its materialised twin (the
> party-widening case was live). Fix: ONE canonical flattener (`pricing/services/flattening.py`, built on
> the shared `intervals.py` algebra + `segment_card_rules`) that all four consume; projection is now eager
> and byte-identical to carryover **by construction** (shared `map_anchor_sources` builder); the
> cross-producer equivalence suite (`pricing/tests/test_cross_producer_equivalence.py`) pins 9 grids
> pointwise (tie-break, interior/Feb-29/weekday-shift collisions, single-day slivers, party widening, POA,
> min-nights, uplift, fallback-only) plus byte-identical snapshots.
>
> Intentional behaviour deltas (all disclosed in `data_migration/CUTOVER.md` §Rate rule overlap resolution):
> (1) loader adopts split-not-clip — interior collisions keep BOTH sides, single-day remainders persist,
> party-clipped losers keep ALL surviving brackets, resolution runs post-capacity-clamp, bare legacy_id on
> the lowest surviving bracket; row counts shift, so reconcile `expected_gap=3727` stays a
> recalibrate-at-next-dry-run placeholder. (2) band-less/shadowed anchor periods no longer project (they
> priced nothing; fallback-only anchors still project an empty-grid context priced at `fallback_nightly`;
> affects `stay_length_bounds` only). (3) projected collision segments take the winner's (`bands[0]`)
> min/max nights — matching the materialised twin; `MinNightsNotMet` can flip vs the old lazy behaviour.
> (4) collision fragments in projected quotes snapshot deterministic negative synthetic period ids
> (`QuoteLine.period_id` / `winning_period_id`; plain int fields, FE renders unknown ids label-less).
> Bonus: fixed a pre-existing 0013 replay landmine (deferred FK triggers vs deferred CREATE INDEX).
>
> _Original ticket preserved below for context._

# BUG-016 — Rate-grid disjointness/precedence reimplemented by four producers; a projected quote can price differently from its materialised twin

- **Severity:** 🔴 Bug (money divergence — the number a guest was quoted can differ from the rows they accepted)
- **Source:** the 2026-07-02 backend complexity audit (duplicated rate-resolution)
- **Files:** `pricing/services/projection.py:199–245` (in-memory synthesis),
  `pricing/services/carryover.py:69–97` (`_unclaimed_segments`) + `:213–244`
  (segment→period→band), `data_migration/loaders/pricing.py:177–295`
  (`resolve_rate_band_overlaps` / `_subtract_party`) + `:685–723`,
  `pricing/services/period_backfill.py:59–100`,
  `pricing/services/rates.py:59` (`pick_band_for_night`, lowest-pk tie-break),
  `pricing/services/segmentation.py:99` (`segment_card_rules` — the *shared*
  part)

## Problem

"Flatten the rate grid to (date × party)-disjoint bands, lowest-pk wins,
namespace collision fragments as `#seg{n}`" is the invariant that makes a rate
grid single-valued. `segment_card_rules` (`segmentation.py:99`) is correctly
shared — but the **precedence + collision + fragment-namespacing** rules around
it are copy-derived in **four** independent producers that must all agree:

- `projection.py:199–245` — synthesises bands in memory for a *projected* quote
  (dates outside materialised periods), picking lowest-pk via
  `pick_band_for_night`.
- `carryover.py:69–97,213–244` — materialises next-year periods/bands from an
  anchor; its own docstring states the invariant these copies must jointly
  preserve: "so a projected quote and its materialised twin price identically."
- `data_migration/loaders/pricing.py:177–295,685–723` — the legacy loader's
  own overlap-subtraction + sort.
- `period_backfill.py:59–100` — the period-hierarchy backfill.

The lowest-pk / source-pk tie-break alone appears in `pick_band_for_night`
(`rates.py:59`), the carryover claim order, and the loader sort — three copies
of the same precedence rule.

## Why it's a bug (not just duplication)

The four paths price the **same** villa/date/party and are contracted to agree,
but nothing pins them together. A change to the tie-break, or to Feb-29 /
zero-length / collision handling, in one producer silently desyncs a *projected
quote* from the *materialised rows a user just accepted* — i.e. the guest is
shown one price and the booking is built on another. That is a money-correctness
divergence that can exist today (any asymmetry between projection and carryover
produces it) with no single test asserting all four flatten identically.

## Proposed fix

- Extract **one** "flatten anchor → disjoint bands with precedence + fragment
  ids" service (building on `segment_card_rules`) and have projection,
  carryover, the loader, and period_backfill all consume it — one precedence
  rule, one collision policy, one fragment-namespacing.
- Add a **cross-producer equivalence test**: for a fixture grid, assert the
  projected synthesis and the materialised carryover produce byte-identical
  bands (same dates, party ranges, prices, fragment ids) — the test the
  invariant currently lacks.

## Acceptance

- `grep` finds a single implementation of the disjointness/precedence/fragment
  rule; projection, carryover, loader, and backfill call it.
- A test proves a projected quote and its materialised twin price identically
  across at least the tie-break, collision, and Feb-29/boundary cases.

## Dependencies

Related to GAP-056 (rate-model restructure that created these producers),
Q-018 (rate reductions — will add another rule these copies must all learn),
BUG-013/BUG-014 (occupancy-band flattening lineage). Independent of Q-024.
