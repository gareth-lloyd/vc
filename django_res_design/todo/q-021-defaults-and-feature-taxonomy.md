# Q-021 — Seed group defaults + curate the feature taxonomy

- **Severity:** Question (content/governance) + seeding
- **Source:** 2026-06-11 new-villa setup transcript review
- **Files:** `properties/models/finance.py` (`GroupFinance`),
  `properties/models/settings.py` (`GroupSettings`),
  `properties/models/features.py` (`Feature`, `FeatureCategory`),
  seeding entrypoints (`manage.py seed_dev`, production seed/cutover)

## Problem

The transcript is a catalogue of de-facto defaults and vocabulary the
loader re-enters per villa or improvises:

- **Finance/settings defaults**: deposit "should really default to
  required at 30%"; security deposit applies to "pretty much every villa"
  (usually fixed amount); commission is percentage; check-in 16:30 /
  check-out 10:30 unless stated. Interim deposit is rare (~1 villa) —
  keep available, not prominent.
- **Always-included features**: housekeeping, gardening, pool cleaning on
  essentially every villa; kitchen/dining/sitting room near-universal.
- **Unsettled vocabulary**: housekeeping frequency ("daily" vs "6 days a
  week" — "we need to agree what we're going to put"); near-duplicate
  options causing hesitation ("never quite sure if it's covered parking
  or parking"); services-on-request differ by region (Corfu offers much
  more than the small islands).

The new architecture already has the right mechanism — nullable
`PropertyFinance`/`PropertySettings` fields inheriting from
`GroupFinance`/`GroupSettings` — the defaults just need to be **seeded**,
and `Feature` rows are being created fresh, so now is the cheapest moment
to curate the taxonomy.

## Proposed direction

1. Seed `GroupFinance`/`GroupSettings` for the production cutover group(s):
   deposit required / PERCENT / 30; security deposit required / FIXED;
   commission PERCENT; check-in 16:30 / check-out 10:30. (Changeover day
   and min nights vary per villa — leave unset at group level.)
2. With the loader, agree and record: housekeeping-frequency vocabulary
   (decide whether it's a feature variant, a structured field, or
   standardised prose), the parking taxonomy, and the canonical
   included-features starter set applied to new villas.
3. Optional, low priority: region-aware suggestions for services-on-request.

## Acceptance

- Group default rows seeded (dev seeder + cutover path) and asserted by a
  test on `effective_*` resolvers.
- Feature/vocabulary decisions recorded in `10-decisions.md`; `Feature`
  seed list updated; ambiguous near-duplicates merged or clarified.

## Dependencies

GAP-022 (per-property ordering) and Q-019 (room-derived features) shape
the same `Feature` surface — coordinate the seed list.
