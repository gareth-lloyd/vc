# Q-020 — Description sections: spec enum vs the sections actually written

> **🟡 PARTIAL PROGRESS (2026-08-07)** — the enum is no longer four sections.
> `LOCATION` and `WEB_DESCRIPTION` were added by the WebDesc/Location loader
> work, and `INTERNAL_NOTES` landed with the villa-description-sections change,
> which also fixed the SPA pinning a stale four-value section list (any
> property carrying a `location` or `web_description` row failed the response
> parse and collapsed the whole Descriptions panel — the migrated copy was
> loaded but invisible). **The ticket stays open** for the two questions this
> did not touch:
>
> 1. the summary **short/long** split — still flattened into one `OVERVIEW`;
> 2. **interior/exterior** — legacy `Interior1/2`/`Exterior1/2` currently land
>    as image-slot captions (`data_migration/loaders/property_children.py:92`),
>    not description sections.
>
> A third question was **opened** by this work: legacy `VillaMaster.Notes` maps
> to `FURTHER_INFO` (`data_migration/loaders/properties.py:243`) but has no
> editing surface anywhere in the legacy Properties UI, so its audience is
> undetermined. If the prod snapshot shows it reads as internal, those rows
> should move to `INTERNAL_NOTES`. Query to run once `ResSystem-prod` is stood
> up (`LEGACY_DATABASE_URL` is currently unset and there is no mssql service in
> `docker-compose.yml`):
>
> ```sql
> SELECT TOP 20 Id, LEFT(Notes, 200) FROM VillaMaster
> WHERE Notes IS NOT NULL AND LTRIM(Notes) <> '';
> ```
>
> Any such remap must land **after** the SPA accepts `internal_notes` (it now
> does), scoped to `section="further_info"` AND
> `legacy_id__endswith="-further_info"` so hand-authored copy stays put.

- **Severity:** Question (customer-facing parity check)
- **Source:** 2026-06-11 new-villa setup transcript review
- **Files:** `properties/enums.py` (`DescriptionSection` — see the banner above
  for the current value set; it was four when this ticket was raised),
  `properties/models/descriptions.py`,
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
