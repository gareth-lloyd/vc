# GAP-039 — Enquiry list/dashboard enrichment to the Ben/owner mockup

> **🟨 PARTIAL (2026-06-19)** — Core enrichment shipped on local `main`
> (`8f9e37b`…`135b582`); a few mockup affordances remain as follow-ups.
> **Shipped:** read columns — Region, Villa, Holiday Dates, Sales Person, Flex?
> (interim `Specific / ± N days / Flexible` label), Stage (read-only badge) —
> plus serializer/filter exposure of `lead_status`/`lost_reason` (Units 1, 5);
> the audited `:set-lead-status` action with an **inline Lead-Status dropdown**
> in the grid (Units 2, 6); lead-status & salesperson (incl. `— Unassigned —`)
> filters, a page-size selector (25/50/100), and stage tabs with live counts
> that exclude the terminal Dead/Converted stages (Unit 7); schemas + en/el i18n
> (Unit 4). **Remaining (follow-ups):**
> (a) inline **Sales Person** assign dropdown — currently read-only display;
> (b) inline **Stage** transition dropdown — deliberately read-only this ship
> (transitions stay on the action buttons; the inline-dropdown variant conflicts
> with `05-reservations.md` "stage advances only via transition methods" and is
> a deferred decision);
> (c) inline **Dead → `lost_reason`** dropdown in the cell — `lost_reason` is
> read-only, set via the existing `:close` action;
> (d) **date-range filter** UI control — `created_after`/`created_before` are
> plumbed end to end (params → `toQuery` → backend `CharFilter`s) but no picker
> is rendered yet;
> (e) the **Action (delete, ADMIN-gated)** column and the leading **select**
> checkbox column;
> (f) page-size `10` option (mockup lists 10/25/50/100; shipped 25/50/100).
> The `± 7 days` flex variant remains with GAP-043. Quality gate green.

> **🧱 Shared-enum foundation landed (2026-06-18)** — the stage, lead-status, and
> lost-reason vocabularies the enriched grid needs now exist on `Enquiry`: stage
> values renamed to the mockup wording (`new` / `progressing` / `quote_sent` /
> `follow_up` / `dead` / `converted`), `lead_status` (`hot/warm/cold/dead`,
> default `warm`) with a `(lead_status, status)` index and a `set_lead_status()`
> mutation that writes a `LEAD_STATUS_CHANGED` event, and a structured
> `lost_reason` for the Dead-with-reason dropdown — commits `48d1014`…`b90f833`,
> reservations migrations `0032`–`0035`. Remaining GAP-039 work is the
> **serializer/filter/inline-PATCH exposure** of these fields plus the richer FE
> table (region, villa name, date range, flex label, inline dropdowns, stage tabs).
> Note: the **Flex?** column still uses the existing `is_flexible` +
> `flexibility_days` until GAP-043 widens that vocabulary.

- **Severity:** Gap (frontend-led; small serializer/filter additions) — operator UX
- **Source:** 2026-06-17 owner Loom ("the dashboard … is a little bit light … go
  into the version that Ben and I designed") + the mockup at
  https://vc-new-res-system.netlify.app/ → **Quotes & Enquiries**. The mockup's
  columns match the real legacy `/quote` list reconstructed in
  [GAP-010 §4](gap-010-quote-enquiry-analyzed-wrong-codebase.md) (VC Ref, Name,
  Villa Name, Enq/Quote Date, Person, Holiday Dates, Flex?).
- **Status:** 🟨 Partial (2026-06-19) — core enrichment shipped; see the banner
  above for the remaining follow-up affordances.
- **Files:**
  - `frontend/src/features/enquiries/EnquiriesListPage.tsx`, `columns.tsx`
  - `django_res/reservations/serializers/enquiry.py`,
    filters (region, salesperson, lead status, date range)

## Problem

The current enquiry list carries a lean column set. The owner wants the richer
table he and Ben designed, so the sales team has full context in the grid.

## Proposed fix

Match the mockup table.

**Columns:** select · **VC Ref** · Name · **Villa Name** · **Region** ·
Enq/Quote Date · **Sales Person** (inline assign dropdown) · **Holiday Dates**
(date range) · **Flex?** (`Specific dates` / `+/- 3 days` / `+/- 7 days` /
`Flexible`) · **Stage** (inline dropdown) · **Lead Status** (inline
`Hot/Warm/Cold/Dead`; when Dead, a reason dropdown) · Action (delete,
ADMIN-gated per legacy `Enquires.razor:113`).

**Controls:** stage tabs with live counts (`All / New Enquiry / Progressing /
Quote Sent / Follow-up`), page-size selector (10/25/50/100), Lead-status filter,
Sales-person filter (incl. `— Unassigned —`), free-text search (name / villa /
ref).

Inline `assigned_to`, `stage`, and `lead_status` dropdowns persist immediately
(the list already uses this pattern for some fields). Add the missing read
fields (region, villa name, date range, flex label) to the list serializer and
the salesperson/region/date-range filters.

## Acceptance

- The list renders every column above; inline salesperson / stage / lead-status
  edits persist without a full reload.
- Stage tabs show correct counts and filter the grid; salesperson, lead-status,
  date-range filters and search work together.
- Quality gate green (vitest + eslint + prettier + tsc; pytest for the
  serializer/filter additions).

## Dependencies

- **Stage + Flex vocabulary** is shared with
  [GAP-038](gap-038-enquiry-quote-stacking-conversion-metric.md) (stages +
  lost-reason) and [GAP-043](gap-043-quote-builder-multi-week-range.md) (the
  `+/- 7 days` / `Flexible` flex options exceed today's 0–3 cap). Land the enum
  once and reuse.
