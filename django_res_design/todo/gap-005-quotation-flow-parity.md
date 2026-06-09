# GAP-005 — Enquiry → Quotation flow: parity gaps vs legacy

- **Severity:** Gap (frontend + backend) — tracker
- **Source:** stakeholder-driven parity review of the enquiry→quotation
  flow against legacy `ResSystem/` (the combined `Booking.razor` screen),
  plus a second round of stakeholder UX feedback (2026-06-08) — the "spine
  UX overhaul" program below.
- **Key files:**
  - `frontend/src/features/quotations/` (builder, detail, send dialog)
  - `frontend/src/features/enquiries/` (list, detail layout,
    `EnquiryFormDialog`, `tabs/ActivityTab`, `tabs/NotesTab`)
  - `frontend/src/components/layout/Sidebar.tsx` (nav items)
  - `frontend/src/features/contacts/components/ContactPicker.tsx` +
    `useSearchContacts` (template for the new `GuestPicker`)
  - `django_res/reservations/models/{quotation,guest,enquiry}.py`
  - `django_res/reservations/serializers/enquiry.py`,
    `views/guest.py`, `core/fields.py` (`CIEmailField`),
    `reservations/apps.py` (AuditLog)
  - Legacy reference: `ResSystem/NewResSystem/Pages/Bookings/Booking.razor`,
    `ResSystem/Database/Data/TblVillaQuotationMaster.cs`

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
> ⏸ deferred — #3 auto-hold (needs hold surface), #9 two-pane builder,
> #10 availability badges (blocked on
> [Q-013](q-013-rate-card-incomplete-pricing.md)), #11 TBC mode,
> #12 line pagination.
> ❌ dropped — #8 PDF (beyond-legacy overreach; see below).

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
     quote/email.

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

8. **Quotation PDF** — ❌ **DROPPED (2026-06-02).** Beyond-legacy
   overreach. Legacy sends quotations as inline HTML email only — no PDF,
   no attachment, no download/print (legacy's `wkhtmltopdf` is used solely
   for booking receipts). The rebuild already matches legacy with the rich
   HTML preview + copy-to-Outlook path, so a guest-saveable PDF is net-new
   scope, not parity. Decision #19 reversed in
   `../product-design/07-api-schema-reconciliation.md`; the `:pdf` endpoint
   stub is removed. Revisit post-v1 only on a concrete requirement — the
   `render_quotation_html` seam would back it cheaply.
9. **Builder shape diverges from spec.** → **Owned by the Spine UX overhaul
   below (M4)** — the merged enquiry+quote workspace is the builder rework.
   Design specs a two-pane,
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

## Follow-up surfaced by code review (not yet fixed)

- **Builder line create/update changeover.** ✅ Resolved by
  [GAP-007](gap-007-changeover-autoshift-parity.md). There is no separate
  changeover *validation* to reinstate: changeover is now always handled by the
  auto-shift inside `PricingEngine.quote()`, and `QuotationLineViewSet._reprice`
  reflects the engine's shifted `date_from`/`date_to` (plus
  `changeover_shifted_from`) back onto the response. A line added or re-dated
  via `POST`/`PATCH /quotations/{id}/lines` on a forbidden changeover day is
  nudged forward and surfaced rather than rejected. (Hold placement on this
  builder path stays deferred per #3 — holds are still only placed by
  `create_from_enquiry`.)

## Spine UX overhaul (stakeholder feedback — 2026-06-08)

A second round of feedback asks us to collapse the split enquiry/quote UI into
one dense "spine" where agents live, and to enrich client capture. Item #9
above — builder shape — is part of **M4** here.

**Parity decisions (from legacy `ResSystem/`).** Guest required on a quote;
agent optional; both may be present (`VillaQuotationMaster`: `ClientDetailsId`
NOT NULL, `AgentId` nullable — `TblVillaQuotationMaster.cs`). No standalone
quotes (`EnquireId` NOT NULL). The rebuild already matches on guest/agent
(`Quotation.guest` PROTECT/required, `Quotation.agent` nullable —
`reservations/models/quotation.py:23–41`); `Quotation.enquiry` is tightened to
NOT NULL here (M4). ⇒ the searchable "client" is the first-class **`Guest`**
(`GET /guests?search=`, already has `phone` + `contact_method`); the optional
travel agent stays a separate `accounts.Contact` field via the existing
`ContactPicker`.

> **Not strict parity:** legacy captured the guest as per-enquiry free-text and
> has no confirmed deduped guest *search* or per-client *history* view. M3
> (search + history) is an **enhancement enabled by the rebuild's first-class
> `Guest`**, not legacy parity.

**Status (2026-06-09).** ✅ **M1–M4 landed.** M2 shipped with the `people-model-cleanup` merge; M1 (phone +
`contact_method` capture/display/audit/carry) and M3 (`GuestPicker` +
`useSearchGuests`, ACTIVE-only; `GET /guests/{id}/enquiries` enriched with
`quote_count` + `converted_booking`; collapsible history panel) landed in
`feat/gap-005-m1-m3` (merged to `main`). Notes for M4 and future work:
> - `converted_booking` = the **most-recently-created non-archived** booking off
>   the enquiry's ACCEPTED quotations' selected lines (`null` otherwise); ties on
>   `created_at` currently resolve arbitrarily (no secondary sort — minor).
> - Synthetic `booking-` quotation exclusion now routes through the shared
>   `Quotation.objects.real()` / `QuotationLine` queryset method (landed in M4);
>   the enquiry quote-stack prefetch and the `/enquiries/quotes` list both use it.
> - The converted-booking chip passes a status **label** to `StatusBadge`, which
>   colour-codes off the raw enum → the chip renders neutral (cosmetic).
> - `GuestEnquiryHistory` fetches on mount even while collapsed (the header shows
>   the count); gate the rows fetch on expand if it shows up in profiling.

### M1 — Capture enrichment (additive; no IA change) ✅ done

- **Expose `phone` on enquiry reads.** `Enquiry.phone` / `Guest.phone` exist;
  the enquiry **write** serializer exposes `phone` but the **list/detail read**
  serializers don't (`reservations/serializers/enquiry.py`). Add `phone` to the
  read serializers and surface it on the form and detail header for new **and**
  existing enquiries.
- **Contact preference.** Add a denormalized `Enquiry.contact_method` mirroring
  the existing denormalized `phone`/`email` pattern (`enquiry.py:41–45`) so
  anonymous inbound web enquiries (`guest=null`) can carry it; capture
  phone-vs-email (vs SMS) in `EnquiryFormDialog` and show it on the detail
  header. Carry it forward onto `Guest.contact_method` (already exists,
  EMAIL/PHONE/SMS) when a Guest is resolved/created. Add `contact_method` to the
  Guest AuditLog field set (currently untracked — `reservations/apps.py:25–40`).

### M2 — Guest as a deduped directory (foundation for M3) ✅ done

**Data model settled in [`../people-model-cleanup.md`](../people-model-cleanup.md)**
(decisions logged in [`../10-decisions.md`](../10-decisions.md)). M2 is the
*implementation* of that record. In brief: `Guest.email` becomes optional and
stays **non-unique**; `phone` normalized to E.164 (`phonenumbers`); contactability
+ actionable-preference CHECK constraints replace the fake email-required; the
synthetic `enquiry-{id}@noemail.local` fabrication in
`SaveQuoteDialog.tsx:117–126` is removed; **dedup is advisory** (resolve-or-create
suggestion + operator-confirmed `Guest.merge()`), *not* a hard unique index.
Legacy duplicate collapse is a human-confirmed `Guest.merge()` pass (no auto-merge
by email). See the record for the full field/constraint list and migration order.

### M3 — Existing-client search + enquiry history (enhancement) ✅ done

- **Guest search in the enquiry form.** Build a `GuestPicker` + `useSearchGuests`
  mirroring `contacts/components/ContactPicker.tsx` + `useSearchContacts`. Wire
  into `EnquiryFormDialog`: selecting an existing Guest prefills
  name/email/phone/preference and **links `enquiry.guest`** (reuse the row — no
  duplicate); "create new" keeps today's free-text path. The optional **agent**
  stays a separate `ContactPicker` field.
- **Per-guest history endpoint.** Add `GET /guests/{id}/enquiries` returning
  enquiry summaries enriched with quote-count and the converted booking's
  reference/status (reverse relations `Guest.enquiries` / `.quotations` exist).
  Render a collapsible "Enquiry history" panel (collapsed by default — see mock)
  when an existing Guest is selected.
- **Mock-vs-real caveat (general).** The mock's reference formats
  (`QVC-####`/`VCB-####`) and status words ("Booked"/"Completed") are
  illustrative only. Use the real `QVC####` (quotation) / `VC####` (booking)
  formats ([GAP-006](gap-006-legacy-reference-format-parity.md), `core/refs.py`)
  and map to real enum values (booking status is DRAFT…CHECKED_OUT/CANCELLED,
  not "Completed").

### M4 — IA consolidation + merged workspace (highest-risk; last) ✅ done

> **Done (2026-06-09).** Shipped across `feat/gap-005-m4` (single-spine enquiry
> workspace + inline `<QuoteBuilder>`, slices 1–4, merged to `main`) and
> `feat/gap-005-m4-final` — **5a:** the cross-enquiry quotes pipeline is preserved
> as a "Quotes" tab under Enquiries (`/enquiries/quotes`, reusing the quotes
> table); **5b:** the standalone Quotes nav item + `/quotations` list/builder
> routes are removed (redirecting to the tab), `QuotationBuilderPage` deleted.
> The `Quotation.enquiry` FK was **already** `NOT NULL` + `PROTECT` (migration
> `0022`) — the "`SET_NULL` → `PROTECT`" note below was stale; **no migration this
> phase**.

- **One nav item.** ✅ Standalone "Quotes" sidebar item + `/quotations`
  list/builder routes removed; the pipeline survives as the `/enquiries/quotes`
  tab, and `/quotations` + `/quotations/new` redirect there. `/quotations/:id`
  remains a deep-link target, not a top-level destination.
- **`Quotation.enquiry` → NOT NULL.** ✅ Already `null=False` +
  `on_delete=PROTECT` (migration `0022`, pre-dating this phase; the earlier
  "`SET_NULL` → `PROTECT`" framing was stale — it was already `PROTECT`).
  `SaveQuoteDialog` always sends `enquiry: enquiry.id` and agent-direct quotes
  create a lightweight enquiry first, so no live UI creates enquiry-less quotes.
- **Merged enquiry+quote workspace.** Clicking an enquiry lands on a combined
  workspace (replacing the Details/Activity/Notes landing **and** the separate
  `/quotations/new?enquiry=` builder): client/criteria header + existing
  quotations for the enquiry inline (`EnquiryDetailSerializer` already inlines
  `.quotations[].lines[]`) + the builder (reuse
  `QuoteCriteriaForm`/`QuoteResultsList`/`QuoteCart`/`SaveQuoteDialog`, already
  enquiry-seeded in `QuotationBuilderPage.tsx:70–79`). **Preserve Activity &
  Notes** as secondary panels (side rail / collapsible sections), reusing the
  existing `ActivityTab`/`NotesTab` components. This subsumes #9 above.

**Acceptance (per milestone).** M1: phone + preference visible/editable on new
and existing enquiries. M2: the guest-create path resolves-or-suggests an
existing match on normalized email/phone (advisory — operator confirms reuse),
the `@noemail.local` fabrication is gone and no new synthetic-email rows are
written, channel-less rows are dispositioned (`ARCHIVED`) before the
contactability CHECK is added; `email` stays **non-unique**. M3: guest search
returns existing guests, selection reuses the row and reveals a collapsed
history panel with correct refs/statuses. M4: one Enquiries nav item; clicking
an enquiry lands on the merged workspace showing existing quotes + builder +
activity/notes; no enquiry-less quote-creation path; `Quotation.enquiry` NOT
NULL constraint present.

**Sequencing.** M1 → M2 → M3 → M4 (cheap/additive first; M3 depends on M2's
dedup being meaningful; the page rearchitecture + FK migration land last).

## Approach

Tracker ticket — each P1/P2 item (and each spine-overhaul milestone) becomes
its own ticket. Suggested first slice on the **parity** track: **#1 + #2
together** (preview modal + copy-to-clipboard share the server-side HTML
render), since they're the highest operator-pain and one render path backs both
the SMTP and manual paths. The **spine overhaul** track sequences separately as
M1→M4 above.

## Dependencies

- #3 (auto-hold) depends on the availability/hold surface.
- #4 discount-cap and #9 incomplete-pricing depend on open design
  questions ([Q-013](q-013-rate-card-incomplete-pricing.md)).
- [SMELL-002](smell-002-quotation-expire-draft.md) (quote expiry) is
  related but tracked separately.
