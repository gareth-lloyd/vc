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
FeaturesTab. The direction is sound; verification surfaced several
under-scoped realities that must be handled:

- **Migration is the highest-risk step.** This is NOT a simple `AlterField`
  to `through=`: Django drops the auto-managed M2M table and every existing
  Property↔Feature link with it. Use `SeparateDatabaseAndState` (rename the
  existing M2M table in the DB + add the `sort_order` column, while Django's
  state swaps to the through model) or a copy-then-swap data migration. Ship
  a test asserting row counts are preserved across the migration.
- **Legacy loader rewrite.** `data_migration/loaders/property_children.py`
  (~line 164) currently `GROUP BY`s away `VillaFeaturesMappings.MappingOrder`
  — the exact ordering data this ticket exists to restore. The loader MUST be
  rewritten to `SELECT` and persist `MappingOrder` into `sort_order`;
  otherwise links survive but ordering is lost.
- **Serializer write/read handling.** `PropertyWriteSerializer` exposes
  `features` as a writable plain M2M; `ModelSerializer`'s `.set()` cannot
  populate a through model carrying extra fields, so explicit write handling
  is required. On the read side, `feature_ids` won't reflect order without
  `Meta.ordering` on the through model plus walking `PropertyFeature`. Both
  sides must be handled.
- **FeaturesTab is a tab rewrite, not a pattern copy.** Unlike `RoomsTab`'s
  flat sortable list, `FeaturesTab` is a category-grouped *checkbox* grid.
  Converting it is a `Set` → ordered-array change end-to-end, and there is an
  unresolved flat-vs-grouped ordering UX decision (the `@dnd-kit` pattern in
  `RoomsTab.tsx` / room `sort_order` is a reference, not a drop-in).
- **Audit registration (FG-017 has landed, merged from main).**
  `properties/apps.py` now registers property children via `audit.track()`,
  and `core/tests/test_audit_registry.py`'s `EXPECTED_TRACKED_MODELS` fails
  CI if a property-child model is unregistered. Deselecting a feature
  hard-deletes a `PropertyFeature` row, so the new through model MUST add an
  `audit.track()` call AND an `EXPECTED_TRACKED_MODELS` entry in the same
  commit.

Fallback option if we want to avoid the through model: a curated global
canonical order. Rejected by default — the transcript indicates per-villa
judgement — but record the choice in `10-decisions.md` either way.

## Acceptance

- Through model + migration preserving current Property↔Feature rows
  (`SeparateDatabaseAndState` or copy-then-swap), with a test asserting row
  counts are preserved — the highest-risk step.
- `property_children.py` loader rewritten to `SELECT` and persist
  `MappingOrder` into `sort_order` (no `GROUP BY` that discards it).
- `PropertyWriteSerializer` has explicit through-model write handling; the
  detail API's `feature_ids` reflect persisted order (through-model
  `Meta.ordering` + walking `PropertyFeature`).
- The new `PropertyFeature` through model is registered via `audit.track()`
  with a matching `EXPECTED_TRACKED_MODELS` entry, in the same commit.
- Reorder persists per property and drives feature order in the property
  detail API response (and therefore the public site).
- FeaturesTab rewritten from category-grouped checkbox grid to support
  ordered selection / drag-drop reorder; new selections append last. The
  flat-vs-grouped ordering UX decision is resolved and recorded.
- `02-properties.md` updated to reflect the reversal.

## Dependencies

Coordinate with Q-021 (feature taxonomy / seed-list curation happens in the
same window). GAP-022 is part of the add-property-flow cluster.
