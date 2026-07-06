# Q-021 — Seed group defaults + curate the feature taxonomy

> **✅ SUPERSEDED (2026-07-02)** — split in two so neither half is orphaned:
> the feature-taxonomy cleanup + room→property derivation half →
> [GAP-067](../gap-067-room-feature-taxonomy-cleanup.md) (de-dupe the ~300-row
> legacy `VillaFeatures` list, drop test/junk rows with link-remap, derive
> property features from room attributes via a data-driven bridge); the
> group-defaults + new-villa seeding half (deposit 30%, security deposit,
> check-in/out times, starter included-features, housekeeping-frequency
> vocabulary) → [GAP-068](gap-068-seed-group-finance-settings-defaults.md).
> The "Villa Groups stay" decision below is preserved and carried into GAP-068.
> No work remains here.
>
> **Note (2026-07-03):** the "Villa Groups stay" decision is later **reversed** by
> [GAP-070](gap-070-remove-groups-global-property-defaults.md) (drop groups +
> inheritance; global `PropertyDefaults` singleton applied at creation), which
> supersedes GAP-068. The confirmed default values still carry into GAP-070's seed.

- **Severity:** Question (content/governance) + seeding
- **Source:** 2026-06-11 new-villa setup transcript review
- **Files:** `properties/models/finance.py` (`GroupFinance`),
  `properties/models/settings.py` (`GroupSettings`),
  `properties/models/features.py` (`Feature`, `FeatureCategory`),
  seeding entrypoints (`manage.py seed_dev`, production seed/cutover)

## Problem

> **Villa Groups stay.** Nick (owner, 2026-06-11 email) proposed doing away
> with Villa Groups, but this was assessed as **premature** — he is reasoning
> from the legacy system where groups were unused. In the rebuild,
> `PropertyGroup` is the inheritance backbone: `GroupFinance`/`GroupSettings`
> are exactly where the seeded defaults in this ticket live (deposit 30%, SD
> required, 16:30 / 10:30, etc.), and `PropertySettings`/`PropertyFinance`
> inherit from them via `effective()`. Q-021 therefore remains valid as
> written — do **not** rearchitect away from groups.
>
> Note the adjacent 2026-06-11 decision that seasons should be defined by
> rental rates (not services) — tracked separately as q-022.

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

Q-019 (room-derived features) shapes the same `Feature` surface — coordinate
the seed list. **GAP-022 (per-property ordering) has since landed (`done/`),**
so its through-model + loader rewrite — previously called out as "the cheapest
moment" to settle the taxonomy — is built. Seed the group defaults and curate
the taxonomy **now**, standalone; there is no longer a ticket to ride along
with.
