# BUG-014 — `RateRule` flattened legacy's period→occupancy hierarchy, permitting ragged/misaligned bands

- **Severity:** 🔴 Bug (structural / correctness footgun) — the model allows rate
  states legacy could not represent, enabling silent mis-edits and defeating a
  grid-based editor. No wrong-money-out *today*, but it blocks a correct editing UX
  and lets bad shapes exist.
- **Source:** 2026-07-01 rate-workbench UX investigation. The unified rate editor
  wanted a clean date×occupancy matrix; the flattened `RateRule` shape makes that
  matrix dishonest.
- **Files:**
  - `django_res/pricing/models/rate.py` (`RateCard` 57-81, `RateRule` 84-138 —
    `date_from/date_to` **and** `min_party/max_party` on the same row)
  - migration EXCLUDE constraint (card × daterange × party) — pricing migration 0010
  - legacy shape it diverged from: `ResSystem/Database/Data/VillaSeasonRate.cs`
    (period parent) + `VillaOccupencyPrice.cs` (occupancy children)
  - engine consumer: `django_res/pricing/services/engine.py` (`quote`,
    `covering_bands`)

## Problem

Legacy modelled rates as a **two-level hierarchy**: a `VillaSeasonRate` is a
*date period*, and its `VillaOccupencyPrice` children are the *occupancy bands
inside that period*. Because the bands are children of the period, every band in a
period shares that period's dates **by construction** — legacy is "aligned within a
period, free-form across periods." A band whose date span diverges from its period
is structurally impossible.

The new model **flattened** both levels into one `RateRule` row carrying
`date_from/date_to` *and* `min_party/max_party`, with no parent grouping. The only
guard is a Postgres EXCLUDE constraint forbidding *overlap* on
(card × daterange × party). Nothing forces the bands that make up a period to share
dates. So a single card can legally hold:

- Rule A `[Jun 1 – Jun 28, party 2–4]`
- Rule B `[Jun 1 – Aug 2, party 5–6]`

— i.e. **ragged** bands with different date spans per occupancy band. This shape
was never expressible in legacy.

**Why it bites:**

- **Editing UX.** A date×occupancy matrix (rows = date segments, cols = party
  bands) assumes a grid. With ragged rules there is no shared segment axis: a cell
  can be backed by a rule that spans several "rows," so editing that cell silently
  mutates a wider period than the operator sees. A faithful editor is forced into a
  free-form rules table or a 2-D "rate-map," losing the clarity of a grid.
- **Reasoning.** Downstream code (`covering_bands`, fan-out, summaries) must handle
  arbitrary raggedness rather than a clean per-period band set.

## Proposed fix (Option B — reintroduce the hierarchy)

Restore legacy's structure at the model level:

- Add a **`RatePeriod`** (working name) under `RateCard`: `date_from`, `date_to`,
  `min_nights`/etc. — the date-scoped container (≈ `VillaSeasonRate`).
- Make occupancy prices **children of the period** (≈ `VillaOccupencyPrice`): a
  band row carries `min_party`/`max_party` + `nightly`/`weekly`/`is_poa`, and
  inherits the period's dates. Either a new `RateBand` child, or `RateRule` keyed to
  a `RatePeriod` FK with its date fields removed.
- Constrain: bands within a period are disjoint on party; periods within a card are
  disjoint on dates. Raggedness becomes **impossible by construction**, matching
  legacy and making a grid editor correct.

This also gives the recovered `VillaOccupencyPrice` rows (see BUG-013) a natural
home — one period, N band children — instead of N flat rules.

**Migration:** existing flat `RateRule` rows must be grouped into periods
(group by `card × date_from × date_to` → period; each becomes a band child). Rare
genuinely-ragged rows (from multiple single-`PartySize` legacy rows on overlapping
dates) need splitting/period-cloning; enumerate and report them.

### Cheaper alternative (if schema change is deferred): Option A — UI convention

A frontend-only stopgap: the editor treats a **date segment** as first-class and
always writes bands that share the selected segment's exact dates, so *new* edits
are always a clean grid; pre-existing ragged rules are shown with an "irregular"
marker that edits the specific rule (never a phantom cell). Does not fix the model,
but makes the workbench honest now. Track as the interim; BUG-014 is the durable
fix.

## Acceptance

- Model prevents a card from holding two bands with the same party range but
  different date spans (constraint or structural — periods own dates).
- Migration groups existing `RateRule` rows into periods idempotently; a report
  lists any rows that couldn't be cleanly grouped.
- Engine (`quote`, `covering_bands`) reads the hierarchy and produces identical
  quotes to the pre-change flat model for non-ragged data (parity tests).
- The rate-workbench matrix can rely on a per-period band set (no phantom/spanning
  cells).

## Dependencies / relations

- Pairs with [BUG-013](bug-013-migration-drops-villaoccupencyprice.md) — recovering
  `VillaOccupencyPrice` and giving it a period parent are the same shape of work;
  do them together if possible.
- Touches the engine contract — coordinate with the finance rewrite / BUG-009 so
  the model change lands once, not twice.
- Sibling RateRule integrity tickets: BUG-002 (zero-length range),
  BUG-003 (POA vs price).
- Context: `q-022-seasons-defined-by-rates.md`,
  `q-023-partial-week-nightly-composition.md`, `04-pricing.md`.
