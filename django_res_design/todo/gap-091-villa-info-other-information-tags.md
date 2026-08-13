# GAP-091 — Villa info becomes structured "Other information" tags + a free-text box (WP-searchable)

- **Severity:** 🟢 Gap (customer-facing parity + WordPress search). Backend +
  frontend + data-migration.
- **Source:** 2026-07-20 Nick screen-recording (`Recording-20260720_134424`,
  reviewed 2026-08-11). Transcript `[02:35–03:46]`, recap `[04:16–04:22]`;
  legacy Features screen captured at `[03:10]`, public rendering at `[02:46]`.
- **⛔ Blocked on:** the preloaded tag vocabulary. Nick hovers the `Add +`
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
