# GAP-005 — Enquiry → Quotation flow: parity gaps vs legacy

- **Severity:** Gap (frontend + backend) — tracker
- **Source:** stakeholder-driven parity review of the enquiry→quotation
  flow against legacy `ResSystem/` (the combined `Booking.razor` screen).
- **Key files:**
  - `frontend/src/features/quotations/` (builder, detail, send dialog)
  - `django_res/reservations/models/quotation.py` (`Quotation`,
    `QuotationLine`)
  - `django_res/reservations/views/quotation.py` (`:pdf` stub)
  - Legacy reference: `ResSystem/NewResSystem/Pages/Bookings/Booking.razor`

## Context — the one-screen → three-stage split

Legacy `Booking.razor` (1,151 lines) is a single combined workspace:
enquiry capture + quote pricing + full payment schedule + concierge +
owner details + email, all at once. The rebuild deliberately splits this
into **enquiry → quotation → booking** stages (design improvement #7).
That split is the root cause of most "missing" findings: several things
the operator did *at quote time* in legacy now live one stage later, on
the booking.

## Resolved by stakeholder decision (NOT gaps — record only)

- **Payment schedule at quote time → keep deferred to booking.** Legacy
  showed deposit / balance / security-deposit, deposit-override % (10–80%),
  editable balance-due-date, and CC-Pre-Auth vs Bank-Transfer method on
  the quote screen (`Booking.razor:298–343`). These fields live on the
  `Booking` model (`booking.py:89–92`) and the quote stays price-only.
  **Decision (2026-06-02): accepted as designed.** No indicative schedule
  on the quote.
- **Concierge → booking-only.** Legacy let operators build concierge
  line-items on the quote screen (`Booking.razor:389–449`). The rebuild's
  concierge system is a booking tab
  (`features/bookings/tabs/ConciergeTab.tsx`, `reservations/models/concierge.py`).
  **Decision (2026-06-02): accepted; no quote-time concierge.**

## Foundation correctness gaps (found while grounding the parity work)

Two bugs sat *underneath* the cosmetic parity gaps; the parity work would have
sat on sand without them. Both are now fixed on branch
`gap-005-quotation-flow-parity` (Phase 0 of the program of work).

- **F1 — API-created quotation lines were never priced.**
  `QuotationLineViewSet.perform_create` only called `serializer.save()`; there
  was no pricing hook on `QuotationLine` and no signal, so lines saved via
  `POST /quotations/{id}/lines` (the builder's save path) landed with
  `total=0` and an empty `pricing_snapshot`. Only
  `QuotationService.create_from_enquiry` priced correctly, which masked the bug
  in `seed_dev` data. **Fix:** extracted `QuotationService.price_line` and call
  it from `perform_create`/`perform_update` (non-manual lines), under
  `select_for_update` per [FG-006](fg-006-modify-without-select-for-update.md).
- **F2 — The quotation email was a content-less stub.**
  `quotation_sent_handler` passed only guest/agent/reference (and never the
  `{{ property_name }}` the template referenced); the MJML body had no line
  items, dates, prices, or terms. Guests received an email that didn't contain
  the quote. **Fix:** new shared render seam
  `reservations/services/quotation_render.py`
  (`build_quotation_context` / `render_quotation_html`) now backs the email,
  the `:preview` endpoint, and copy-to-clipboard from one source of truth.

## Open implementation gaps (design says yes, code says no)

Priority order below reflects operator-pain / spec-commitment.

> **Implementation status (branch `gap-005-quotation-flow-parity`):**
> ✅ done — #1 preview-before-send, #2 copy-to-Outlook, #4 imagery,
> #5 per-line discount, #6 inclusions, #7 price-override-with-reason.
> ⏸ deferred — #3 auto-hold (needs hold surface), #8 PDF (render seam is
> ready; PDF is the fast-follow), #9 two-pane builder, #10 availability
> badges (blocked on [Q-013](q-013-rate-card-incomplete-pricing.md)),
> #11 TBC mode, #12 line pagination.

### P1 — Send experience (highest operator-touch)

1. **Preview-before-send is missing.** Design improvement #9 mandates
   every outbound send shows an editable **subject + intro + sign-off**
   with an HTML preview, then an awaited send. Today
   `components/SendQuotationDialog.tsx` is a bare confirm dialog
   (title + Cancel/Confirm, no preview, no editable copy).
2. **Path B (copy-to-Outlook) has no payload.** Backend
   `:mark-manually-sent` flips state, but the design's whole point — a
   **"Copy HTML to clipboard"** button handing the operator the rendered
   quote to paste into Outlook — isn't built. Nick specifically wanted
   Outlook formatting control; without the clipboard payload, "manual
   send" just changes status.
3. **48h auto-hold checkbox on send** — specced on the preview modal
   (improvement #7); not implemented. Depends on the availability/hold
   surface.

### P2 — Visual richness (property imagery)

4. **No property imagery anywhere in the quote flow.** Legacy renders the
   villa hero image on every line of the quote workspace
   (`Booking.razor:91–92`, CDN `vc2.mojodev.co.uk/{folder}/{villaId}/{img}`)
   — operators quote while looking at the villa. Our flow is text-only end
   to end: `QuoteResultsList.tsx` (name + price rows), `QuoteLinesPanel.tsx:48`
   (name cell), `QuotationDetailLayout.tsx:86` (name or `#id`). The
   `quoteOption` schema (`schemas.ts:89`) and `pricing/serializers/quote.py`
   carry **no image URL**. The design only specs a thumbnail on the search
   result card and never carries imagery to saved lines, detail, or the
   guest-facing quote.
   - **Cheap to close — data already exists:** `PropertyImage` model +
     serializer (`properties/serializers/image.py`) has `image`,
     `sort_order`, and a set-hero concept. Slice: (a) add `hero_image_url`
     to the quote-search/quote-bulk response, (b) render it on result card +
     lines panel + detail lines, (c) carry it into the guest-facing
     quote/email/PDF.

### P2 — Line richness

5. **Per-line discount** — design specifies a quote-line discount
   (amount or %); `QuotationLine` has no discount field (only `total`,
   `is_manual`, `notes`). (`adjustment`/`discount` exist on `Booking`,
   not the quote.) Discount-cap rule is also still open in the design.
6. **Inclusions per line** — design calls for a per-line `Inclusion`
   field defaulting from the villa/rate-card and shown to the guest;
   the model has only a single `notes` TextField.
7. **Price override with required reason** — design wants an inline
   override + audit reason; we have `is_manual` + `total` but capture no
   reason.

### P3 — Artifacts & builder shape

8. **Quotation PDF** — `GET /quotations/{id}:pdf` returns 501
   (`views/quotation.py`). Legacy renders quotation HTML/templates;
   confirm whether a guest-saveable PDF is wanted.
9. **Builder shape diverges from spec.** Design specs a two-pane,
   always-visible **cart** with inline price-edit under each result card,
   drag-reorder, and a "From £X / To £Y" range. We built a linear wizard
   (`QuoteCriteriaForm → QuoteResultsList → QuoteLinesPanel →
   SaveQuoteDialog`). Functional, but not the reviewed UX.

### P4 — Minor / polish

10. **Availability badge richness** — design wants
    `Available / Hold-able / Partial / Unavailable` + an "incomplete
    pricing — manual quote" flag on result cards
    (blocked on [Q-013](q-013-rate-card-incomplete-pricing.md)); current
    results list is simpler.
11. **TBC occupancy mode** — legacy TBC checkbox (`Booking.razor:119`)
    clears adults/children for flexible group quotes; `QuotationLine`
    requires both. Confirm if still needed.
12. **Quotation line list hard-caps at 50** (frontend `hooks.ts` TODO) —
    acceptable for real quotes; wire a paginator only if a quote ever
    exceeds the cap.

## Approach

Tracker ticket — each P1/P2 item becomes its own ticket. Suggested first
slice: **#1 + #2 together** (preview modal + copy-to-clipboard share the
server-side HTML render), since they're the highest operator-pain and one
render path backs both the SMTP and manual paths.

## Dependencies

- #3 (auto-hold) depends on the availability/hold surface.
- #4 discount-cap and #9 incomplete-pricing depend on open design
  questions ([Q-013](q-013-rate-card-incomplete-pricing.md)).
- [SMELL-002](smell-002-quotation-expire-draft.md) (quote expiry) is
  related but tracked separately.
