# GAP-038 — Enquiry pipeline: stage taxonomy + quotes-to-convert metric

> **🧱 Shared-enum foundation landed (2026-06-18)** — the stage taxonomy this
> ticket needs now exists on `Enquiry`: values renamed to the dashboard
> vocabulary (`new` / `progressing` / `quote_sent` / `follow_up` / `dead` /
> `converted`), a structured `EnquiryLostReason` (`lost_reason` + a dead-requires-
> reason constraint), and the orthogonal `lead_status` temperature — commits
> `48d1014`…`b90f833`, reservations migrations `0032`–`0035`. Remaining GAP-038
> work is the **quotes-to-convert metric** (count `kind=OPERATOR` quotations
> only — until the GAP-020 `kind` enum lands, use `Quotation.objects.real()`
> plus an enquiry-side synthetic filter) and the per-quote status surfacing /
> serializer exposure built on these enums.

- **Severity:** Gap (backend + frontend) — sales-pipeline reporting
- **Source:** 2026-06-17 owner Loom walkthrough of Quotes & Enquiries + the
  Ben/owner mockup at https://vc-new-res-system.netlify.app/ (the mockup mirrors
  the real legacy 4-screen flow corrected in
  [GAP-010 §4](gap-010-quote-enquiry-analyzed-wrong-codebase.md)).
- **Status:** Open. Builds on the **already-shipped** quote-stacking work — do
  not re-spec it (see below).
- **Files:**
  - `django_res/reservations/models/enquiry.py` (status enum + lost-reason),
    `models/quotation.py` (per-quote status surfacing)
  - `django_res/reservations/serializers/enquiry.py` (`quote_count` exists —
    add conversion fields)
  - `frontend/src/features/enquiries/EnquiryDetailLayout.tsx`, `tabs/`,
    `columns.tsx`

## Problem

The owner frames the funnel as **lead → qualified → enquiry → quote**, with
"as many quotes as we can stack below each inquiry … to track how many quotes it
takes to convert each inquiry." Three sub-gaps:

1. **Stage taxonomy diverges.** The mockup pipeline is **New Enquiry →
   Progressing → Quote Sent → Follow-up**, plus a terminal **Dead** carrying a
   required reason (`Found something else` / `Availability` / `Chose a different
   destination` / `Couldn't get group consensus` / `Don't know`). Current
   `Enquiry.status` is `NEW / CONTACTED / QUOTED / LOST / CONVERTED` with an
   orthogonal `lead_status` temperature (`HOT/WARM/COLD/DEAD`). The two vocabs
   need reconciling so the list, the funnel, and the lost-reason all line up.
2. **No quotes-to-convert metric.** "Very important" per the owner — we capture
   `quote_count` per enquiry (M3) but report nothing on how many quotes an
   enquiry took to convert, nor a funnel/conversion view.
3. **Per-quote status not surfaced in the stack.** The mockup's "Live Enquiries"
   panel shows each stacked quote (`QVC-3708/Q1…Qn`) with its own status
   (Sent / Accepted / Deposit Due / Deposit Paid / Booked). Today the enquiry
   detail inlines `.quotations[].lines[]` but doesn't present the per-quote
   lifecycle chip in this stacked form.

## Already shipped (do NOT redo — frame against it)

[GAP-005](gap-005-quotation-flow-parity.md) M3/M4 delivered the stacking
foundation: `Quotation.enquiry` is NOT NULL + PROTECT (many quotes per enquiry),
`EnquiryDetailSerializer` inlines the quotations + lines, the enquiry quote-stack
prefetch uses `Quotation.objects.real()`, and `GET /guests/{id}/enquiries` is
enriched with `quote_count` + `converted_booking`. **The stacking and the count
already exist** — this ticket is the *taxonomy reconciliation* + the *conversion
metric/reporting* + the *per-quote status chip*, not the stack itself.

## Proposed fix

- Reconcile the stage model: decide whether to extend `Enquiry.status` to the
  mockup's vocabulary (Progressing/Follow-up) or map them to existing states,
  and add the structured `lost_reason` enum gated on the Dead/LOST terminal.
  Record the decision in `10-decisions.md`. (Keep `lead_status` temperature
  orthogonal — it already exists.)
- Add conversion fields to the enquiry serializer: `quotes_to_convert` (count of
  quotations created up to and including the accepted one; null until converted)
  and expose enough for a funnel/conversion report. A dedicated reporting
  endpoint can follow separately.
- Surface the per-quote status chip in the stacked "Live Enquiries" view, reusing
  `StatusBadge`.
- **Out of scope:** Zoho CRM integration ("we're gonna connect to at some
  point") — note as future, do not build.

## Acceptance

- Enquiry stages match the agreed vocabulary; a Dead/LOST enquiry requires a
  reason; the list and detail reflect it.
- An accepted enquiry reports `quotes_to_convert`; a funnel/conversion figure is
  derivable. (backend test)
- The stacked quotes under an enquiry each show their lifecycle status.
- Quality gate green (pytest + ruff + mypy; vitest + eslint + tsc).

## Dependencies

- Sibling of [GAP-039](gap-039-enquiry-dashboard-enrichment.md) (the list shares
  the stage + lost-reason vocab) and [GAP-005](gap-005-quotation-flow-parity.md)
  (stacking foundation). Coordinate the stage enum once across all three.
