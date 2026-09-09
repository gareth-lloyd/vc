# GAP-091 — Villa info becomes structured "Other information" tags + a free-text box (WP-searchable)

> **✅ RESOLVED (2026-09-09, local `main` unpushed)** — shipped on
> `feat/gap-091` in 5 units (efaabddf enum + migration, 75f95dd4 tag catalog
> + seed_dev, bb99e66e loader split, b989fb3d Zoho block, 791061db frontend).
> **What shipped:** `DescriptionSection` loses `villa_info` and gains
> `other_information` + `rooms` (`section` widened to 32, migration
> `properties/0007` renames existing rows in place). Tags are `Feature` rows
> in the `other-information` `FeatureCategory` assigned via `PropertyFeature`
> — no new model, `service_type` untouched, classification is by category
> (legacy never discriminated tags by ServiceType either). The Features tab
> renders an "Other information" section: the ordered tag list (a filtered
> view over the tab's single `order`, saved by the same Save button; `order`
> is rebuilt `[...main, ...tags]` only on a mutation, never on mount) plus the
> free-text box with its own Save/Clear. The Zoho villa payload gains
> `other_information: {tags, description}`; tag links are excluded from
> `features[]` (facet on `tags[].slug`). The loader writes
> `FeatureDescription → other_information` and `RoomDescription → rooms`
> (GAP-092's blurb, no UI yet) and unfuses a pre-split DB on re-run
> (`CUTOVER.md` §6e).
>
> **The blocker resolved itself in the legacy schema:** there is no `Tags`
> table. "Other Information" is legacy feature category **Code 60 /
> `VillaFeaturesCategory.Id=8`** of the single `VillaFeatures` catalogue;
> live vocabulary mapped to it (Dec-2024 snapshot, legacy id): Wheelchair
> access 96, No pets 124, No smoking indoors 125, Children not allowed 126,
> Weddings and events 127, Pets allowed 128, Resident pets 129, Fenced pool
> 130, Service kitchen 131, Staff accommodation 132, No large parties 271.
> Excluded on purpose: `152 Wheelchair accessible` (soft-deleted 2024-07),
> `298 Sea View` (mapped to eight categories; `FeatureLoader` files it under
> Included Features and seeding owns `sea-view` under `outdoor`). **No seed
> migration:** prod/staging get the vocabulary from `FeatureCategoryLoader` +
> `FeatureLoader` (legacy_id `8` / per-row ids, slug `slugify(name)`); dev
> DBs get it from `properties/other_information_catalog.py` via `seed_dev`
> with the same `legacy_id`s stamped so a later loader run adopts the rows
> (a migration-seeded vocabulary would break the exact-count feature tests).
>
> **Ops / partner notes:** (1) tell Limitless — tags moved out of
> `features[]` into `other_information.tags`, facet on `slug`; run
> `zoho_backfill --kinds villa` after deploy (GAP-082 amendment). (2)
> `304 Dev Feature` is live junk under Code 60 and WILL surface as a tag after
> cutover — deactivate it in the Tags admin (GAP-067 drops it). (3) A DB
> loaded before this ships needs the §6e `loadlegacy property` re-run
> immediately post-deploy, no `--since`, before staff edit. **Accepted
> limitations:** per-assignment category + per-villa tag `Description`
> override from `VillaFeaturesMappings` still dropped (GAP-067); links to a
> deactivated feature keep pushing; Feature edits don't re-push villas;
> `duplicate()` clones `other_information` + `rooms` with the tags (public
> copy travels with its tags). GAP-090 keeps the block-set rebuild; GAP-092
> renders `rooms`.


- **Severity:** 🟢 Gap (customer-facing parity + WordPress search). Backend +
  frontend + data-migration.
- **Source:** 2026-07-20 Nick screen-recording (`Recording-20260720_134424`,
  reviewed 2026-08-11). Transcript `[02:35–03:46]`, recap `[04:16–04:22]`;
  legacy Features screen captured at `[03:10]`, public rendering at `[02:46]`.
- **~~⛔ Blocked on:~~ resolved (see banner):** the preloaded tag vocabulary. Nick hovers the `Add +`
  button under *Other Information Tags* at `[03:10]–[03:15]` but never opens
  it, so the full list is not on screen. Only the two assignments on the
  example villa are visible. Pull from the legacy snapshot, or confirm the
  existing `Tags` admin already carries it.
- **Files touched (best-guess):**
  - `django_res/properties/models/features.py` — `FeatureCategory` (L9),
    `Feature` (L28), `PropertyFeature` (L56, has `sort_order` + `is_derived`),
    `Collection` (L97). The infrastructure this needs already exists.
  - `django_res/properties/enums.py:131` — `FeatureServiceType`
    (`amenity / included_service / paid_addon`).
  - `django_res/properties/enums.py:104` — `DescriptionSection`, losing
    `villa_info` (member at `:124`).
  - `django_res/data_migration/loaders/properties.py:237–241` — the
    `FeatureDescription + RoomDescription → VILLA_INFO` concatenation.
  - `frontend/src/features/properties/tabs/FeaturesTab.tsx`.
  - `frontend/src/features/properties/components/DescriptionsSection.tsx`.

## Problem

`villa_info` is a single free-text blob in our app. In legacy it is **two
things on the Features screen**, side by side (`[03:10]`):

- **Other Information Tags** — an ordered list of assigned tags from a
  preloaded vocabulary. Example villa carries `No smoking indoors` and
  `Pets allowed`; add / remove / reorder.
- **Other information description** — a free textarea beside it. Real content
  from the example: *"Licence Number: 0829K112K813200 / It is not possible to
  heat the pool."*

The public villa page (`villacollective.com/athens-riviera/villa-hespera`,
`[02:46]`) renders these under an `OTHER INFORMATION` accordion — a plain
two-column list of tag names, alongside `SERVICES INCLUDED`, `SERVICES ON
REQUEST` and `LOCATION`.

Nick's stated reason for the tags being structured is the one that matters:
*"that obviously means it can then be searchable from the WordPress site"*.
Free text cannot back a facet filter. He also wants the free-text half kept —
*"if there's something quite specific about that villa which could belong in
the house rules, but actually you wanted to split on the front end of the
website, then that's where we put it"* — i.e. it is **not** a fallback for
missing tags, it is public-facing prose with a distinct job. Verbatim: *"So
it's a combination of tags and a description. If we could keep that as is,
that would be great."*

Today the loader also **fuses two unrelated legacy columns** into this one
blob: `FeatureDescription` and `RoomDescription` are joined with a blank line
(L237–241). `RoomDescription` is almost certainly the property-level rooms
blurb GAP-092 is about, not villa info at all.

## Proposed fix

1. **Tags on the existing feature spine** — an "Other information"
   `FeatureCategory` with `Feature` rows for the vocabulary, assigned through
   `PropertyFeature` (which already carries `sort_order` for the legacy
   ordering, and `is_derived=False` for these hand-assigned rows). No new
   model.
   - ⚠️ **`FeatureServiceType` has no fitting member.** These tags are not a
     service (`amenity / included_service / paid_addon`). Decide: a new enum
     member, a nullable `service_type`, or category-only classification.
     Prefer whichever keeps `/features?category=` filtering coherent — see
     BUG-019, which is fixing exactly that endpoint.
2. **Free text** — a property-level "Other information" text field rendered
   beside the tags. Cheapest home is a `DescriptionSection` member
   (`other_information`), reusing `PropertyDescription`; put it on the
   Features tab next to the tags, matching legacy placement.
3. **Drop `villa_info`** from `DescriptionSection`, with a data migration
   moving existing bodies to the new free-text section.
4. **Loader** — split the concatenation: `FeatureDescription` → the new free
   text; `RoomDescription` → GAP-092's property-level rooms blurb. Import the
   per-villa tag assignments once the vocabulary is known.
5. **WordPress** — confirm the tags reach WP as structured values (this is
   the whole justification); coordinate with the villa payload in GAP-082.

## Acceptance

- The tag vocabulary is seeded and assignable per property, ordered, with
  add/remove; assignments survive a loader re-run. (test)
- The free-text box saves independently of the tags and is distinct from
  house rules. (test)
- `villa_info` is gone from `DescriptionSection`; existing bodies migrated,
  not dropped. (migration test)
- Loader writes `FeatureDescription` and `RoomDescription` to different
  places; transform test pins both.
- Tags are exposed in a form WordPress can filter on (payload asserted).
- Quality gate green (backend + frontend).

## Dependencies

- **⛔ Blocked on the tag vocabulary** (above) — everything else can be built
  against a placeholder set, but the seed migration cannot land without it.
- **GAP-090** — shares the `DescriptionSection` migration; sequence together
  so the enum changes once.
- **GAP-092** — takes `RoomDescription`, the other half of the concatenation
  being split here.
- **BUG-019** — `/features?category=` is a silent no-op today and truncates at
  50 rows; the tag admin for this vocabulary needs that fixed to be usable.
- **GAP-067** — room feature taxonomy cleanup; same `Feature`/`FeatureCategory`
  spine, worth landing in a consistent direction.
- Related: GAP-082 (Zoho villa push payload), GAP-028 (WP/Zoho integration).
