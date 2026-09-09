# GAP-103 — Region/Country edits never reach Zoho (no geo push kind, no parent bump)

- **Severity:** 🟠 Gap (a retired region stays selectable in every Zoho
  dropdown until each villa/contact/enquiry embedding it happens to re-push —
  for a stable villa, never).
- **Source:** GAP-102 unit-1 review (2026-09-08). GAP-102 put `slug` /
  `is_active` / `iso3` on the wire; this is the freshness half it did not
  cover.
- **Files touched (when built):**
  - `django_res/integrations/services/zoho_flow.py` — `register_zoho_flow`
    call sites; `ZOHO_FLOW_KINDS`.
  - `django_res/properties/signals.py` — `_VILLA_CHILDREN` omits `Region` /
    `Country` (correctly: they are shared lookups, not villa children).
  - `django_res/integrations/management/commands/zoho_backfill.py` —
    `KIND_ORDER`.
  - `django_res/properties/views/geo.py` — `RegionViewSet` is a writable
    `ModelViewSet` exposing `slug` + `is_active`; admin registers both models.

## Problem

Region and country objects are only ever delivered as **snapshots inside**
villa / enquiry / quote / booking / contact pushes. No hook re-pushes anything
when a `Region` or `Country` row itself changes (`register_zoho_flow` is
called only for Person / Property / Enquiry / Quotation / Booking), so:

- Staff `PATCH /api/regions/{slug}` `{is_active: false}` → every payload Zoho
  already holds keeps `is_active: true` (and the old slug after a re-slug)
  until that parent is next saved.
- Regions with no villa never reach Zoho at all, so a dropdown "matching our
  values" (the 2026-09-08 Limitless ask: *"if we can just get a dump of
  those"*) cannot be assembled from embedded keys.
- "The same" region arrives in two shapes across records.

## Proposed fix

The GAP-102 ticket's own remedy for extras applies verbatim — a first-class
push, not a fan-out: `register_zoho_flow(Region, kind="region", …)` (country
rides inside the region payload, as today) with its own webhook URL from
Limitless on the GAP-096 coordination pattern, and a `region` stage at the
**front** of `zoho_backfill.KIND_ORDER` (organisation → **region** → contact
→ villa → enquiry → quote → booking). Fan-out (a Region save bumping every
villa in it) is the wrong shape: one region edit → N villa pushes.

Sequence the geo loader `DeletedBy`/orphan filtering (71 vs 57 legacy
regions, GAP-102 ticket text) **before** the first backfill of this kind, or
the retired rows get pushed once and then have to be retired again in Zoho.

## Acceptance

- Saving a `Region` (incl. `is_active` flip and re-slug) enqueues exactly
  one `region` push; saving a `Property` in it enqueues none extra. (test)
- `zoho_backfill` pushes `region` before any kind that embeds one. (test)
- A region with no villa reaches Zoho. (verified in the CRM — GAP-097)

## Dependencies

- **GAP-096** — same coordination pattern (URL from Limitless, env var,
  backfill ordering).
- **GAP-102** — resolved; supplies the keys this ticket keeps fresh.
- **CHECK-002** open decision (Countries of Interest picklist) — this is the
  "picklist we seed from our region list" option made maintainable.
