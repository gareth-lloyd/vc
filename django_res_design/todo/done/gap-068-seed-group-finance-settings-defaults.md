# GAP-068 — Seed group finance/settings defaults + new-villa starter set

> **❌ DROPPED (2026-07-06) — superseded by
> [GAP-070](done/gap-070-remove-groups-global-property-defaults.md), now landed
> (local `main` unpushed).** GAP-070 dropped property groups and runtime inheritance,
> so there is no `GroupFinance`/`GroupSettings` left to seed. The confirmed default
> **values** here (deposit 30% / SD fixed / commission % / 16:30 / 10:30) carried
> forward as the seed for GAP-070's global `PropertyDefaults` singleton; the
> included-features starter-set half belongs with **GAP-067**. Never built as written.
> The "Villa Groups stay" context below is the stance GAP-070 reversed.

- **Severity:** Build (seeding) — carries the group-defaults half of the
  superseded **Q-021**
- **Source:** 2026-06-11 new-villa setup transcript / email round; split out of
  Q-021 when its feature-taxonomy half became [GAP-067](gap-067-room-feature-taxonomy-cleanup.md)
- **Files:** `properties/models/finance.py` (`GroupFinance`),
  `properties/models/settings.py` (`GroupSettings`), seeding entrypoints
  (`manage.py seed_dev`, production seed/cutover), a test on the `effective_*`
  resolvers, `10-decisions.md`

## Context — Villa Groups stay (preserved from Q-021)

> Nick (owner, 2026-06-11 email) proposed doing away with Villa Groups, but this
> was assessed as **premature** — he is reasoning from the legacy system where
> groups were unused. In the rebuild, `PropertyGroup` is the inheritance
> backbone: `GroupFinance`/`GroupSettings` are exactly where these seeded
> defaults live, and `PropertySettings`/`PropertyFinance` inherit from them via
> `effective()`. Do **not** rearchitect away from groups.

## Problem

The 2026-06-11 transcript is a catalogue of de-facto defaults the loader
re-enters per villa or improvises:

- **Finance/settings defaults**: deposit "should really default to required at
  30%"; security deposit applies to "pretty much every villa" (usually a fixed
  amount); commission is a percentage; check-in 16:30 / check-out 10:30 unless
  stated. Interim deposit is rare (~1 villa) — keep available, not prominent.
- **Always-included features**: housekeeping, gardening, pool cleaning on
  essentially every villa; kitchen / dining / sitting room near-universal.
- **Unsettled vocabulary**: housekeeping frequency ("daily" vs "6 days a week" —
  "we need to agree what we're going to put"); services-on-request differ by
  region (Corfu offers much more than the small islands).

The architecture already has the right mechanism — nullable
`PropertyFinance`/`PropertySettings` fields inheriting from
`GroupFinance`/`GroupSettings`. The defaults just need to be **seeded**.

## Proposed direction

1. Seed `GroupFinance`/`GroupSettings` for the production cutover group(s):
   deposit **required / PERCENT / 30**; security deposit **required / FIXED**
   (amount per villa); commission **PERCENT**; check-in **16:30** / check-out
   **10:30**. (Changeover day and min nights vary per villa — leave unset at
   group level.)
2. With the loader, agree and record the **housekeeping-frequency vocabulary**
   (decide whether it's a feature variant, a structured field, or standardised
   prose) and the **canonical included-features starter set** applied to new
   villas. Coordinate the starter set with GAP-067 (it owns the `Feature`
   taxonomy those rows come from).
3. Optional, low priority: region-aware suggestions for services-on-request.

## Owner steer (Q-021 B-round — see `owner-questions-2026-07-02.md`)

- **B1** — confirm the default set every new villa starts with (deposit 30% /
  SD required fixed / commission % / 16:30 / 10:30).
- Housekeeping-frequency wording ("daily" vs "6 days a week").
- The canonical always-included starter set (housekeeping, gardening, pool
  cleaning, kitchen, dining, sitting room?).

## Next steps

1. Land the B-round answers; record in `10-decisions.md`.
2. Seed `GroupFinance`/`GroupSettings` in the dev seeder **and** the cutover
   path; assert via a test on the `effective_*` resolvers.
3. Decide + seed the housekeeping-frequency vocabulary and the starter
   included-features set (with GAP-067).

## Acceptance

- Group default rows seeded (dev seeder + cutover path) and asserted by a test
  on `PropertyFinance.effective(...)` / `PropertySettings.effective(...)`.
- Housekeeping-frequency + included-features decisions recorded in
  `10-decisions.md`; starter `Feature` set applied to new villas.

## Dependencies

- **GAP-067** — coordinate the starter included-features seed (it owns the
  curated `Feature` taxonomy).
- Groups stay (owner-removal deemed premature — see context above).
</content>
