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
