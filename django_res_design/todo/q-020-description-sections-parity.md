# Q-020 — Description sections: spec enum vs the sections actually written

- **Severity:** Question (customer-facing parity check)
- **Source:** 2026-06-11 new-villa setup transcript review
- **Files:** `properties/models/descriptions.py` (`PropertyDescription.section`:
  OVERVIEW / HOUSE_RULES / VILLA_INFO / FURTHER_INFO),
  `django_res_design/02-properties.md` (~line 156 section mapping)

## Problem

The transcript shows the loader writing a richer structure than the new
enum models: **summary** (one-to-two-line short + longer paragraph),
**interior** (short + long), **exterior**, and **location** — each feeding
distinct slots on the public website. The new `PropertyDescription` has
four fixed sections mapped from `VillaMaster` columns
(`WebsiteDescription` → OVERVIEW, etc.), which may have flattened the
short/long split and the interior/exterior/location separation.

Per the standing principle, customer-facing output must match legacy. The
design-spec mapping was derived from the legacy schema, but the
quote/enquiry portion of the spec is already known to have been
reverse-engineered from an incomplete codebase (see GAP-010) — so the
section mapping deserves verification against what the live site actually
renders, not just the columns.

## Proposed direction

1. Verify against the legacy prod snapshot + live website templates which
   description fields exist and where each renders (summary short/long,
   interior short/long, exterior, location vs the four-column mapping).
2. If the loader's structure is real, extend the `section` enum (cheap —
   it's one row per section per property with a unique constraint) and
   update the migration loader mapping; if the four sections genuinely
   cover it, record that and close.

## Acceptance

- Mapping verified against legacy rendering and recorded in
  `02-properties.md`.
- Enum extended + data-migration loader updated if needed; the property
  Details tab edits whatever the final section set is.

## Dependencies

GAP-010 context (spec areas reverse-engineered from the wrong codebase).
Requires the legacy prod snapshot (`ResSystem-prod`) for verification.
