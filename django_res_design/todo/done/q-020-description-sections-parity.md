# Q-020 — Description sections: spec enum vs the sections actually written

> **✅ SUPERSEDED (2026-09-16)** — closed early (todo consolidation) rather than on GAP-090 landing. Its answer has lived in [GAP-090](gap-090-description-block-set-parity.md) since 2026-08-11, which states "answers + supersedes Q-020"; keeping this open only counted the same work twice. Nothing left here to act on.
>
> _Original ticket preserved below for context._

> ⏸ **SUPERSEDED-PENDING (2026-08-11) — folded into
> [GAP-090](gap-090-description-block-set-parity.md); drop when that lands.**
>
> **Answered.** The 2026-07-20 Nick screen-recording
> (`Recording-20260720_134424`) captures the legacy Descriptions screen
> directly at `[01:48]`, which is the verification step 1 below asked for.
> The suspicion was right on both counts: the loader's structure is real, and
> our enum **has** flattened it. Legacy holds nine fields as short-"sub" /
> long-"para" pairs — `Web des 1 (top larger text)` + `Web des 2 (opening
> para)`, `Interior sub` + `Interior Para`, `Exterior Sub` + `Exterior Para`,
> `Location sub` + `Location Para`, plus `Video Url`. Interior and exterior
> are absent from our enum entirely, and `_write_descriptions`
> (`loaders/properties.py:247–254`) joins each surviving pair with `"\n\n"`.
>
> Step 2's "extend the enum" is too small a fix — the sub/para split means the
> section set is replaced, not extended, and the fused rows need a loader
> re-run rather than a string split. GAP-090 carries that work.

- **Severity:** Question (customer-facing parity check) — **answered**
- **Source:** 2026-06-11 new-villa setup transcript review
- **Files:** `properties/enums.py:104` (`DescriptionSection` — four values when
  this was filed, seven now; GAP-090 replaces the set),
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
