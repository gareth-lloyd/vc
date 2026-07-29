# GAP-005 — Enquiry → Quotation flow: parity gaps vs legacy

- **Severity:** Gap (frontend + backend) — tracker
- **Source:** stakeholder-driven parity review of the enquiry→quotation
  flow against legacy `ResSystem/` (baseline corrected 2026-07-02 by
  GAP-010: legacy was a 4-screen flow, not the single `Booking.razor`
  workspace; see
  [`../legacy/quote-enquiry-reference.md`](../legacy/quote-enquiry-reference.md)),
  plus the 2026-06-08 stakeholder UX feedback round (the "spine UX
  overhaul", shipped — see the prune note).
- **Key files (for the surviving items):**
  - `frontend/src/features/quotations/components/` — `SendPreviewDialog`
    (auto-hold checkbox home), `QuoteResultLine.tsx` (availability badges)
  - `frontend/src/features/quotations/hooks.ts:41,62–66` — the 50-line cap
  - `django_res/reservations/models/quotation.py:260–261`
    (`QuotationLine.adults`/`children` — TBC mode)
  - `django_res/reservations/services/quotations.py:144`
    (`HoldService.place` — the existing hold path)

> **✂️ Pruned 2026-07-29 (consistency review).** This tracker's body was
> ~90% shipped history and several premises had gone stale against the
> code; the detail lives in this file's git history and the tickets named
> below. What was cut and why:
>
> - **Phase 0 foundations, parity items #1/#2/#4/#5/#6/#7, and the spine
>   overhaul M1–M4** all shipped (per the previous status header; M4's
>   merged workspace + the `/enquiries/quotes` IA are live). #8 (PDF) was
>   dropped 2026-06-02. #9 (builder shape) was subsumed by M4 and then
>   concretely delivered by GAP-043 (multi-week builder) — the "⏸ deferred"
>   glyph it carried contradicted M4/GAP-043 being done.
> - **Stale premises removed:** "`QuotationLine` has no discount field" —
>   it does (`reservations/models/quotation.py:264`, shipped with the #5
>   per-line-discount work); "`adjustment`/`discount` exist on `Booking`" —
>   both columns were dropped by SMELL-020 (reservations.0005); the entire
>   `Guest`/`GuestPicker`/`GET /guests` spine (M1–M3 text) — the `Guest`
>   model and `/guests` surface were retired by GAP-045's `Person`
>   unification (the shipped features live on, re-homed onto
>   `Person`/`/contacts`).
> - **Owner-Loom follow-up wave** spun out long ago and is done:
>   GAP-038/039/043/044 (and GAP-040/041/042 for customer-profile).
>
> What remains open is exactly the four items below.

## Open items

### 1. 48h auto-hold checkbox on send (was #3)

Design improvement #7 specs an auto-hold checkbox on the send-preview
modal. Not built: sending a quote places no hold. The hold machinery
itself exists (`HoldService.place`, called from
`QuotationService.create_from_enquiry`; line holds move on reprice via
`move_line_hold`) — the missing piece is the send-dialog affordance wiring
a hold per sent line, plus its expiry story (48h default).

### 2. Availability badge richness (was #10)

Design wants `Available / Hold-able / Partial / Unavailable` + an
"incomplete pricing — manual quote" flag on result cards. The
incomplete-pricing flag + manual-quote path landed with
[Q-013](done/q-013-rate-card-incomplete-pricing.md) (no-rate villas render
as flagged manual-quote cards); the richer `Hold-able / Partial` taxonomy
on `QuoteResultLine` is still open.

### 3. TBC occupancy mode (was #11)

Legacy's TBC checkbox (`Booking.razor:119`) cleared adults/children for
flexible group quotes. `QuotationLine.adults` is still required
(`PositiveSmallIntegerField`, no default; `children` defaults 0 —
`quotation.py:260–261`), so a party-TBC line cannot be represented.
Confirm with the owner whether TBC is still wanted before building
(occupancy-band pricing from GAP-044 has since made party size
price-relevant, which raises the design cost of "no party yet").

### 4. Quotation line list hard-caps at 50 (was #12)

Still true: `QUOTATIONS_PAGE_SIZE = 50` and the lines fetch sees only
DRF's default first page with no `page_size` override
(`frontend/src/features/quotations/hooks.ts:41,62–66` — the TODO
documents that a >50-line quote would silently truncate the convert
dialog and lines table). Acceptable for real quotes; wire a paginator
only if a quote ever exceeds the cap.

## Dependencies

- Item 1 builds on the existing `HoldService` path (no new hold surface
  needed — that caveat is stale; the affordance + expiry policy are the
  work).
- Item 2 is FE-only over the existing `search-options` availability data;
  coordinate with [GAP-013](gap-013-quote-builder-ux-feedback-loops.md)
  (builder feedback-loop polish on the same result cards).
- Item 3 needs an owner decision first (record in `10-decisions.md`).
- [Q-013](done/q-013-rate-card-incomplete-pricing.md) resolved;
  [SMELL-002](done/smell-002-quotation-expire-draft.md) (quote expiry)
  related but separate.
