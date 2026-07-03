# GAP-050 — Enquiry grid: inline salesperson/stage/lost-reason edits + remaining mockup controls

- **Severity:** Gap (frontend-led; minor view/authz additions) — operator UX;
  follow-up to GAP-039.
- **Source:** Split from
  [GAP-039](done/gap-039-enquiry-dashboard-enrichment.md) on 2026-06-19. GAP-039
  delivered the enriched read columns, the inline **lead-status** edit, and the
  lead-status / salesperson / page-size filters + stage tabs; this ticket is the
  set of mockup affordances it did **not** cover. Mockup:
  https://vc-new-res-system.netlify.app/ → **Quotes & Enquiries**; the column
  set mirrors the legacy `/quote` list reconstructed in
  [the legacy reference §4](../legacy/quote-enquiry-reference.md) (promoted from GAP-010).
- **Status:** Open.
- **Files:**
  - `frontend/src/features/enquiries/columns.tsx`,
    `EnquiriesListPage.tsx`, `components/` (new inline-edit cells, date-range
    control) — mirror the shipped `components/LeadStatusCell.tsx` pattern.
  - `django_res/reservations/views/enquiry.py` (delete authz; any new action).

## Problem

GAP-039 enriched the enquiry grid to the owner/Ben mockup but deliberately
scoped a few affordances to a follow-up: three of the mockup's cells are
inline-editable, the date-range filter has its params plumbed but no UI control,
and the leading **select** + trailing **Action (delete)** columns are absent.

## Proposed fix

1. **Inline Sales Person (`assigned_to`) dropdown** in the grid cell — persists
   via the existing `:assign` action; today the column is read-only display.
   Mirror `LeadStatusCell` (Popover + per-cell mutation + row-click
   `stopPropagation` guard, since `DataTable` rows navigate on click).
2. **Inline Stage dropdown** — ⚠️ **decision first.** `05-reservations.md` states
   stage advances only via transition methods (Send Quote / Convert / Close), so
   an arbitrary inline stage dropdown conflicts with the model. Either (a) keep
   Stage read-only and close this sub-item, or (b) build a constrained dropdown
   offering only legal transitions. Record the decision in `10-decisions.md`
   before building.
3. **Inline Dead → `lost_reason` dropdown** — when an enquiry is Dead, allow
   editing the structured `lost_reason` from the cell (today read-only, set only
   via the `:close` action).
4. **Date-range filter UI** — render a date-range picker bound to the already
   plumbed `created_after` / `created_before` params (params → `toQuery` →
   backend `CharFilter`s already work end to end; only the control is missing).
5. **Action column** — delete, ADMIN-gated (legacy `Enquires.razor:113`), plus a
   leading **select** checkbox column for bulk affordances.
6. **Page-size `10`** option (mockup lists 10/25/50/100; shipped 25/50/100).
7. **Flex? vocabulary widening** — the mockup's Flex? presets
   (`Specific dates` / `+/- 3 days` / `+/- 7 days` / `Flexible`) exceed the
   intake cap: widen `Enquiry.flexibility_days` (`MaxValueValidator(3)` → 21)
   with a migration, add an open **"Flexible"** mode, and surface the preset in
   the intake form + grid column. Orphan-rescued here 2026-07-02: GAP-039
   deferred it to GAP-043, whose shipped builder (arrival-window search, done
   2026-07-02) doesn't need it — the window already runs to ±21 days without
   touching intake — leaving this as the only open home. The builder's
   `enquiryToSearchForm` seeding (`date_from ± flexibility_days`) picks the
   wider values up automatically.

## Acceptance

- Inline salesperson edits — and stage / lost_reason per the decisions above —
  persist without a full reload, with the row-click `stopPropagation` guard
  intact.
- The date-range filter composes with the existing lead-status / salesperson
  filters + search.
- Delete is ADMIN-gated and audited; non-admins see it disabled inside a tooltip
  (per `frontend/CLAUDE.md` "buttons disable, never disappear").
- Quality gate green (vitest + eslint + prettier + tsc; pytest for any
  view/authz change).

## Dependencies

- Builds directly on [GAP-039](done/gap-039-enquiry-dashboard-enrichment.md)
  (delivered grid + the `LeadStatusCell` inline-edit pattern) and the
  `:assign` / `:close` actions already in `reservations/views/enquiry.py`.
- The **Stage-dropdown** sub-item is blocked on the `05-reservations.md`
  stage-transition decision.
- `± 7 days` flex labelling / `flexibility_days` widening now lives HERE
  (item 7) — GAP-043 shipped the builder side without it
  ([done/gap-043](done/gap-043-quote-builder-multi-week-range.md)).
