# GAP-067 — Feature taxonomy cleanup + derive property features from room attributes

> **🟡 PARTIALLY RESOLVED (2026-07-06)** — The **derivation half** (the "enter
> once" / triple-entry fix) shipped in 4 units on local `main` (unpushed);
> **taxonomy curation remains open** (see below). Shipped:
> `PropertyFeature.is_derived` (migration `0032`) + is_derived-aware
> `_sync_feature_order` (clobber-proof, promote-on-manual-add) + read-only
> `derived_feature_ids` + retrieve prefetch (`9265267`); `recompute_derived_features`
> service reconciling derived links to the union of `RoomAttribute.implies_property_feature`
> across a property's rooms, wired into every room create/update/delete + the
> seeding stage, with `duplicate()` cloning manual-only features (`79d4bfb`);
> `recompute_derived_features` management command (resumable real sweep,
> rolled-back `--dry-run`) + CUTOVER §6c + `design/decisions.md` Live row
> (`18a36e0`); FE read-only "From rooms" chips in FeaturesTab (manual list
> excludes derived, save is manual-only) + en/el i18n (`771d12c`).
> Data-driven bridge only — no hardcoded room→feature map.
>
> **Still open (deferred — a follow-up ticket):** the **taxonomy-curation** half
> below (§"The property-level feature taxonomy is dirty" / Q-021) — merging the
> duplicate/junk legacy `Feature` rows (`Aircon` ×5, `Wheelchair access`/`accessible`,
> `TAGSSSSSSSSSSS`, …), remapping `PropertyFeature` links to survivors, and
> recalibrating the `reconcile_legacy` `Feature` gap. It is gated on owner-steer
> #1 (canonical wording) and only has real data to act on at cutover, so it was
> split out. Canonical pattern when built: `Person.merge` / `merge_country.py`.
> Also deferred: GAP-068 starter included-features seed; a live admin hook to
> recompute when a curator edits `RoomAttribute.implies_property_feature`.

- **Severity:** Build + content governance — answers the A1 "enter once" promise,
  supersedes the feature-taxonomy half of **Q-021** (seeding half → GAP-068)
- **Files:** `properties/models/features.py` (`Feature`, `FeatureCategory`,
  `PropertyFeature`), feature seed/curation, `properties/services/*` (derivation),
  `data_migration/loaders/*` (feature loader), `10-decisions.md`
- **Depends on:** GAP-064 (room attributes are the derivation source); coordinate
  the starter included-features seed with **GAP-068**

## Problem

Two connected messes:

1. **The property-level feature taxonomy is dirty.** It is being migrated fresh,
   so now is the cheapest moment to curate it (Q-021).
2. **Triple entry.** The A1 transcript: wheelchair access is entered on the room,
   on the features page, and in the description — all from memory ("I'd make sure
   I put that on the features page as well"). GAP-064 makes the room the structured
   source; this ticket makes the **property feature derive from it** so it is
   entered once.

## Legacy evidence (production dump — the mess to clean)

From the `VillaFeatures` inserts (~300 rows), concrete problems:

- **Duplicate air-con** (5): `Aircon`, `Air con (partial)`, `Air con (throughout)`,
  `Aircon (bedrooms)`, `Aircon (selected rooms)` — plus `Air con (partial)`
  again. These exist because there was no per-room aircon field (GAP-064 fixes
  the cause).
- **Duplicate accessibility:** `Wheelchair access` **and** `Wheelchair accessible`.
- **Near-duplicates that cause loader hesitation** (Q-021): `Parking` /
  `Parking spaces` / `Covered parking`; `Kitchen` ×2; `Sitting room` ×2;
  `Cinema room` ×2; `Jacuzzi` ×2; `Table tennis` ×2; `Gym` ×2; `Bathroom products` /
  `Bathroom Prooducts` (typo); `Padel court` / `Padle Court` / `Padel tennis court`.
- **Test / junk rows shipped to prod:** `TAGSSSSSSSSSSS`, `test ss`, `Delete Test`,
  `Dev`, `Developer Testing`, `Dev test 12345`, `Dev Feature`, `Feature I`,
  `Feature 18 ED`, `Tag 1`, `Indoor Tag 1`, `LIVING SPACE i/II`, `Sync Feature Updated`.
- Categories exist and are sane: `Living Space`, `Indoor Features`, `Outdoors`,
  `Outdoor Features`, `Included Features`, `Services On Request`, `Collections`,
  `Other Information` — these map onto the new `FeatureServiceType`
  (amenity / included_service / paid_addon) + `FeatureCategory`.

## Proposed direction (opinionated)

### 1. Curate on the way in (Q-021)
- **Merge duplicates** to a canonical row, remapping every `PropertyFeature` link
  to the survivor (no orphaned assignments). Canonical picks: single `Air con`
  (per-villa nuance moves to the per-property `description` override that
  `PropertyFeature`/legacy `VillaFeaturesTags.Description` already supports —
  e.g. "Air con in bedrooms only"); single `Wheelchair accessible`; single
  `Parking` (+ description "covered").
- **Drop the test/junk rows** — but only after confirming **zero** property links
  point at them (query `PropertyFeature`); if any do, remap to the nearest real
  feature or `Other Information`, never hard-drop a linked row (no loss).
- Record every merge/drop decision in `10-decisions.md` with the surviving slug.

### 2. Derive property features from room attributes (kills triple entry)
Room attributes and property features are **separate vocabularies** (GAP-064: a
room-scoped `RoomAttribute` catalog, distinct from the property `Feature`
taxonomy). Derivation is therefore an **explicit, data-driven bridge**, not a
shared-catalog roll-up: each `RoomAttribute` row carries an optional
`implies_property_feature` FK (GAP-064). Where it is set, any room bearing that
attribute derives the linked property `Feature`:

- `RoomAttribute("wheelchair").implies_property_feature` → `Wheelchair accessible`
- `RoomAttribute("sea_view").implies_property_feature`   → `Sea views`
- (curator-controlled — a room-only fact like `ceiling_fan` leaves the FK NULL)

Implementation: a small service hook on room attribute-assignment create/delete
recomputes the derived `PropertyFeature` rows for that property from the union of
its rooms' attributes whose `implies_property_feature` is set. Idempotent
recompute, not incremental diffing (KISS).

**Design calls:**
- **The bridge is data, not code.** A curator ticks "implies X" on the catalog
  row (GAP-064); no hardcoded room→feature map to maintain here.
- **Derive positives; never auto-remove a manually-set feature.** A derived add is
  safe; a derived *delete* could wipe an intentional tag. Mark derived rows
  (`is_derived`) and let the recompute manage only those; manual and derived tags
  don't fight.
- **Only attributes with the FK set are derived.** Pool, chef, parking etc. stay
  hand-assigned — they are not room facts and have no room attribute.

## Legacy translation (no information loss)

- Feature rows and every `PropertyFeature` link migrate first (the feature loader
  already keys on `legacy_id`); **curation runs as an explicit, reviewable step
  after load**, not silently inside it — so the raw legacy taxonomy is always
  reproducible and merges are auditable.
- Merges **remap** links (survivor keeps both sets of properties); drops are
  gated on zero live links. Net: no property loses a feature it had.
- Per-villa feature `Description` overrides (legacy `VillaFeaturesTags.Description`)
  carry across unchanged — that is where "partial / bedrooms only" nuance lands
  once the 5 aircon variants collapse to 1.

## Owner steer (Q-021)

1. **Canonical wording** for the merged sets — esp. `Air con`, `Parking`,
   housekeeping frequency ("daily" vs "6 days a week"). Q-021 already asks this;
   this ticket consumes the answers.
2. **Confirm the derived set** — which `RoomAttribute` rows should carry an
   `implies_property_feature` link (wheelchair, sea view?), or do they prefer
   property-level to stay manual?
3. **Starter included-features set** for new villas (housekeeping / gardening /
   pool cleaning — near-universal per the transcript) — seed it (GAP-068).

## Next steps

1. Land GAP-064 first (derivation needs the room attributes).
2. Build a curation script: duplicate-merge (link remap) + junk-drop (zero-link
   gated), decisions recorded in `10-decisions.md`.
3. Add the room→property derivation service hook (+ `is_derived` flag, recompute
   on room save/delete), with tests.
4. Seed the canonical taxonomy + starter included set (with GAP-068).

## Acceptance

- No duplicate air-con / wheelchair / parking rows; junk rows gone; every merge
  in `10-decisions.md`.
- No property loses a feature across curation (link remap verified; reconcile).
- Ticking wheelchair / aircon on a room creates the property feature automatically;
  manual features untouched by the recompute.
</content>
