# GAP-022 — Per-property feature display ordering dropped vs legacy

- **Severity:** Gap (legacy-parity regression)
- **Source:** 2026-06-11 new-villa setup transcript review (property-loader
  walkthrough of legacy ResSystem)
- **Files:** `properties/models/features.py` (Property↔Feature plain M2M),
  `django_res_design/02-properties.md` (~line 210),
  `frontend/src/features/properties/tabs/FeaturesTab.tsx`

## Problem

Legacy orders a property's features per property
(`VillaFeaturesMapping.MappingOrder`, drag-drop in
`ResSystem/.../PropertyFeaturesContent.razor`) and the loader actively uses
it: order of entry = display order on the website, and she manually
rearranges afterwards so high-value features ("swimming pool should come
higher up") display first. Display order is villa-specific marketing
judgement, not a global constant.

The new design deliberately removed this: `02-properties.md` says "no
per-link metadata in the legacy mapping table beyond audit; plain M2M
wins", and the FeaturesTab is checkbox-only with a global
`Feature.sort_order`. **This is a spec-vs-reality disagreement** — the spec
assumed the mapping order was noise; the transcript shows it's used.

## Proposed fix

Replace the auto-through M2M with an explicit through model
(`PropertyFeature` with `sort_order`, default appended-last), surface it in
the DRF property-features endpoint, and add drag-drop reordering to the
FeaturesTab (the `@dnd-kit` pattern already exists in `RoomsTab.tsx` /
room `sort_order`). Migration must preserve existing links.

Fallback option if we want to avoid the through model: a curated global
canonical order. Rejected by default — the transcript indicates per-villa
judgement — but record the choice in `10-decisions.md` either way.

## Acceptance

- Through model + migration preserving current Property↔Feature rows.
- Reorder persists per property and drives feature order in the property
  detail API response (and therefore the public site).
- FeaturesTab supports drag-drop reorder; new selections append last.
- `02-properties.md` updated to reflect the reversal.

## Dependencies

None. Sibling of Q-021 (feature taxonomy curation).
