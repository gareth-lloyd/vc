# GAP-031 — Show the month context above the availability timeline date range

> ✅ **RESOLVED (2026-06-18).** `monthSpanLabel` (new pure helper) renders the
> spanning month(s) + year above the existing date-range span in the timeline
> window header — single month ("June 2026"), cross-month same-year ("June –
> July 2026"), cross-year ("December 2025 – January 2026"). Month/year text is
> date-fns in the active locale; the dash join is an i18n key (`window.
> month_span_range`, en + el), never a concatenated literal. Vitest covers all
> three cases. FE-only, no API change. Quality gate green.

- **Severity:** Gap (FE polish; sales-team readability)
- **Source:** owner Loom walkthrough 2026-06-17 (availability section, 1:04–1:20):
  "just a minor thing, but I see even the date range here, it'd be really nice to
  see which month this refers to above, but let's make it a little bit easier for
  the sales team."
- **Files:** `frontend/src/features/availability/AvailabilityTimelinePage.tsx`
  (window header).

## Problem

The timeline window header shows a raw date range but doesn't make the **month**
obvious at a glance. Sales scanning the tape want to know quickly which month(s)
they're looking at.

## Proposed fix

Frontend only. Show the spanning month label(s) above the date-range header —
e.g. "June – July 2026" for a window crossing a boundary, "June 2026" when it
sits in one month. Derive from the existing window `start`/`end` already held in
the page (and persisted to the URL). No backend or API change.

## Acceptance

- The timeline header shows the spanning month(s) + year above the date range.
- Single-month and month-crossing windows both format correctly.
- Vitest covers the month-span formatting (single month vs crossing a boundary
  vs crossing a year boundary).

## Dependencies

Sibling of GAP-030 (same timeline header); independent — no backend work.
