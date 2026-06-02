# React SPA Workflow Specification — Villa Rental Management System

This document defines user-facing workflows for the new Django REST + React SPA replacement for the Blazor ResSystem. Each workflow specifies entry points, screen-by-screen steps, decision branches, state transitions, side effects, permissions, failure modes, and deliberate departures from the original.

## Cross-Cutting Conventions (reference for all workflows)

Before the workflows themselves, a few system-wide patterns referenced repeatedly below:

**Optimistic vs awaited operations.** Local UI state mutations (toggling a feature checkbox, dragging a date cell, reordering a list, typing in a notes field with debounced autosave) are optimistic — the UI commits immediately and a toast surfaces failure. Anything that crosses a state machine boundary (deposit Awaiting → Sent, booking Underway → DepositPaid, calendar Hold → Booked), generates an email, or charges a card is **awaited** — a button shows a spinner, the form is locked, the result is reflected in a confirmed-state banner. Money movements are never optimistic.

**Availability rechecks.** Any flow that depends on a date range being available re-validates server-side at submit time, regardless of what the UI shows. The client cached availability is treated as advisory. If the recheck fails, the user is shown a conflict resolution panel (see flow 5 and flow 6).

**Drawers vs full pages.** Entity detail (a booking, an enquiry, a villa) opens in a right-side drawer when triggered from a list / timeline / search result, and in a full page on direct deep link. The drawer is just a chrome variant of the same component tree; URL is still updated (push state) so refresh / share works. Drawer dismiss with unsaved changes → confirm dialog.

**Email previews.** Every outbound email step in every workflow surfaces an in-app preview before send, with an "Edit & send" button that pops a rich-text editor pre-filled from template. No silent email send. (Original Blazor app fires-and-forgets too many emails; we are deliberately gating these.)

**Deep links.** Every entity and every step within a multi-step flow has a stable URL: `/enquiries/:id`, `/quotations/:id/edit`, `/bookings/:id/payments/deposit`, `/properties/:id/calendar?from=2026-06-01&to=2026-06-30`. Stepwise flows (property onboarding, rate-card setup) put the step in the URL too: `/properties/new/step/3-features`.

**Permissions vocabulary.** Roles are: `Operator` (default ops user), `Senior Operator` (price overrides, refunds up to threshold), `Admin` (anything), `Accountant` (read-only on most + refund execution), `Owner` (portal only), `Manager` (portal — owner-adjacent), `Viewer` (read-only). Permission is enforced server-side; the SPA hides actions the user can't perform and replaces them with a "Request from admin" affordance where useful.

**Concurrency.** Every editable entity load returns an `etag` / `updated_at`. Saves include it; server returns 409 on conflict. UI surfaces a side-by-side diff with "keep mine / keep theirs / merge" — see flow 5.

---

## 1. Capture an Enquiry (Operator-Typed)

**Entry points:**
- Global "+" menu → "New enquiry" (`/enquiries/new`)
- Cmd-K → "New enquiry"
- From a phone-call drawer if telephony integration is wired (deep link `/enquiries/new?phone=...`)
- From the inbox sidebar if an inbound email is being triaged

**Steps:**

1. **Screen: New Enquiry form, full page, single column ~720px wide.** The form is split into three collapsible sections, all expanded by default: *Guest*, *Trip*, *Notes & source*. A sticky right rail shows "What happens next: an acknowledgement email will be sent to the guest after save."

2. **Guest section.** Fields: first name, last name, email (validated format, debounced duplicate-check that surfaces "We have an existing contact for jane@example.com — link?" with a *Link* / *Create new* choice), phone (libphonenumber formatted, country-inferred), preferred contact channel (email/phone/whatsapp). Linking to an existing contact is optimistic locally; saving the enquiry persists the link.

3. **Trip section.** Fields: arrival date (date picker with `Flexible ±N days` toggle that adds a numeric stepper), departure date or "duration" (toggle between absolute departure date and nights count — picking one computes the other live), adults count, children count, infants count (each with age fields rendered inline when count > 0). Country and region — region is a dependent dropdown filtered by country; both support multi-select because guests often say "Mallorca or Ibiza". Features — chip multi-select (Pool, Sea view, Sleeps 10+, Pet friendly, etc.) drawn from a managed taxonomy. Budget — optional, currency-aware (currency comes from site context).

4. **Notes & source section.** Free-text notes (rich text, paste-from-email friendly), source dropdown (Phone, Email, Walk-in, Web-form-manual-copy, Referral with sub-field, Other), assigned operator (defaults to current user, can be reassigned), site (defaults to current site context, switchable if user has multi-site permission).

5. **Decision point — duplicate detection.** On blur of the email field, the system queries for existing enquiries from the same email in the last 90 days. If any exist, a non-blocking yellow banner shows "Jane Doe has 2 open enquiries — view / merge". Operator can dismiss or click through. Saving with duplicates does not block but is logged.

6. **Decision point — region/country sanity.** If country is "France" but region selected is "Tuscany", form refuses to submit and surfaces the mismatch inline.

7. **Submit.** Awaited. Button label: "Save enquiry & send acknowledgement". Secondary button: "Save without email" (requires note, e.g., "Already replied manually"). Tertiary: "Save as draft" (no email, enquiry status `Draft`, not visible to other operators in the active list).

8. **Post-submit screen.** Redirect to `/enquiries/:id` in a confirmed-state layout: enquiry summary card at top, timeline showing "Created by Gareth, acknowledgement queued" with a chip for the email status (Queued → Sent → Delivered → Opened, polled). Below: a "Next: build a quotation" CTA that deep-links to flow 2.

**States affected:**

| Entity | Before | After |
|---|---|---|
| Enquiry | (none) | `New` (or `Draft`) |
| Contact (guest) | New or existing | Linked to enquiry; `last_contact_at` bumped |
| Email log | — | One row, `acknowledgement`, status `Queued` |

**Side effects:**
- Acknowledgement email queued (templated, site-branded, includes operator's signature).
- Lead-scoring webhook if marketing integration wired.
- Slack notification to operator's region channel if `notify_on_new_enquiry` flag is on for that site.

**Failure & recovery:**
- Email send fails → enquiry remains `New`, timeline shows red email status, "Retry send" button surfaces. Enquiry is not blocked.
- Save fails (validation/network) → form stays mounted, banner explains, no data loss.

**Permissions:** Operator, Senior Operator, Admin. Viewer cannot save (button disabled).

**Departures from original:** (a) Acknowledgement email preview before send instead of silent fire. (b) Duplicate detection with merge affordance. (c) Drafts as a first-class state. (d) Linking to existing contact at capture time, not later. (e) Region/country sanity validation up-front.

---

## 2. Convert Enquiry to Quotation

**Entry points:**
- From enquiry detail page, primary CTA "Build quotation" (`/enquiries/:id/quote/new`)
- From enquiry list bulk action "Quote selected" (creates one quote with all enquiry constraints merged — rare)
- Direct deep link `/quotations/new?enquiry=:id`

**Steps:**

1. **Screen: Quotation Builder, full page, two-pane.** Left pane (40%): enquiry brief locked at top (dates, party, regions, features, budget, notes) with an "Edit constraints" toggle that locally relaxes search filters without mutating the enquiry. Right pane (60%): villa search results.

2. **Left pane — search & filter.** Constraints derived from enquiry pre-populate. Operator can:
   - Toggle "Strict dates" vs "Allow ±3 days" — surfaces villas that don't quite fit so operator can offer alternatives.
   - Multi-select regions, features.
   - Sleeps ≥ N (defaults to party size).
   - Price band slider (in enquiry currency).
   - Sort: price asc/desc, popularity, distance from coast, custom rank.

3. **Right pane — results.** Each villa shown as a card: hero image, name, region, sleeps, bedrooms, features chips, **computed price for the requested dates** (with breakdown tooltip: nightly × nights + cleaning + tax − any season-specific discount), **availability badge** (Available / Hold-able / Partial conflict / Unavailable, with conflict dates listed). Cards have an "Add to quote" button and a star/save state.

4. **Price computation.** Server computes per-villa price by walking season → rate card → occupancy band for each night in range. Result is cached client-side keyed by `(villa_id, from, to, party_size)` for the session. If a villa's rate card is incomplete for some nights, the card flags "Incomplete pricing — manual quote" and disables auto-add, requiring operator to type the price.

5. **Add to quote.** Clicking "Add" opens a small inline editor under the card: dates (pre-filled), price (pre-filled, overridable with "Override" toggle that forces a reason field), currency (per-site default, switchable), notes shown to guest (optional, e.g. "Owner offering 10% off for direct booking"), internal notes (not shown to guest). Saving adds the line to the quote draft in the cart-style summary at the bottom of the page.

6. **Quote cart (bottom drawer, always visible, collapses).** Lists added villas with thumbnail, dates, price, remove (×), reorder handle. Counter chip: "3 villas in quote". A "Reorder to put recommended first" action. Subtotals not summed across villas because the guest will pick one — instead shown as "From £4,200 / Up to £7,800" range.

7. **Decision point — empty quote guard.** Operator cannot proceed to preview with 0 villas.

8. **Preview & send.** "Preview quote" button opens a full-page modal with the rendered guest-facing quote (HTML email body — no PDF). Editable fields in the email: subject, intro paragraph, sign-off. Villa cards are not directly editable in preview (would have to go back).

9. **Send.** Awaited. Options: "Send to guest now", "Save & send later", "Save as draft". On send, the quotation gets a `QuotationNo` (server-generated, sequential, prefixed by site code), status becomes `Sent`, and the enquiry status advances from `New` → `Quoted`.

10. **Hold dates?** Decision point: a checkbox on the preview modal "Place 48h hold on all quoted villas". Default: off. If on, each villa's calendar marks the date range `On Hold` with auto-expiry (see flow 10 for hold semantics). Holds appear in the quotation summary with a countdown.

**States affected:**

| Entity | Before | After |
|---|---|---|
| Enquiry | `New` | `Quoted` |
| Quotation | — | `Draft` then `Sent` (with `QuotationNo`) |
| Quotation lines | — | One per villa, each with own price |
| VillaCalendar (if hold enabled) | `Available` | `On Hold` for line's date range, with `expires_at` |

**Side effects:**
- Guest email sent (preview-confirmed).
- PDF rendered and attached.
- Owner notifications NOT sent at quote stage (deliberate — see departures).
- Holds expiry job scheduled.

**Failure & recovery:**
- Mid-build a villa becomes unavailable (another operator booked it) → on next price/availability refresh (debounced 30s), card shows "Just became unavailable" red badge with "Find alternative" suggestion. If already added to cart, the cart line shows a warning and blocks send until removed or replaced.
- Email send fails → quotation stays `Draft`, retry button.

**Permissions:** Operator+. Price override above ±15% of computed price requires Senior Operator (UI surfaces approval-request affordance for plain Operator).

**Departures from original:** (a) Side-by-side search & cart pattern rather than the original sequential add-villa modal. (b) Real-time availability badges on result cards. (c) Optional auto-hold checkbox at send (was a separate manual step). (d) Override-reason capture (audit trail). (e) Email preview before send. (f) `QuotationNo` only assigned on send, not on draft, to avoid wasted numbers.

---

## 3. Convert Quotation to Booking (Guest Selected a Villa)

**Entry points:**
- Quotation detail page, each line has "Guest chose this" button.
- Email reply triage drawer (if email integration wired) — surfaces "Convert" CTA when guest's reply references a `QuotationNo`.
- Cmd-K → "Convert quote QN-12345".

**Steps:**

1. **Trigger.** Operator clicks "Guest chose this" on one line. Confirmation dialog: "Convert this option to a booking? Other quoted villas will be marked declined." Confirm.

2. **Screen: Booking conversion form, full page.** Top section is locked, read-only carryover from quotation: villa, dates, rental price (with "Adjust" link that opens override), currency. Below are editable sections.

3. **Section: Lead guest.** Pre-filled from enquiry/quotation contact. Editable. "Payer is different from guest" toggle exposes payer fields (name, email, phone, billing address, company if applicable). Payer is who the deposit/balance invoice is made out to.

4. **Section: Party detail.** Adults/children/infants pre-filled, adjustable. Special requests free text. Arrival/departure times. Flight info optional. Dietary, accessibility.

5. **Section: Money.** Rental price (locked from quote, override with reason). Discount/adjustment (currency or percent, with reason). Deposit % (default from site policy, overridable). Deposit amount (computed from %, overridable; overriding amount unlinks from %). Balance due date (computed as arrival − N days from policy, overridable). Security deposit type (None / Pre-auth hold / BT-refundable) and amount (currency-aware, defaults per-villa). Currency conversion display if any field is in a different currency.

6. **Section: Concierge.** Tier toggle: Quintessential (free, default) / Signature (priced). If Signature, an empty line-item builder is shown (operator can add now or later — see flow 9). Default tier from villa setting.

7. **Section: Agent (if agent-booked).** Toggle "Booked via agent" exposes agent picker (search agencies), commission % override, agent's reference number.

8. **Section: Notes.** Two distinct text areas with labels: "Notes shared with guest" (appears on confirmation) and "Internal notes" (operations-only). Plus "Villa info notes" (passed to the property manager).

9. **Section: Confirmation policy.** Radio: "Confirm immediately on deposit" (default) vs "Requires owner pre-approval" (set by villa setting, overridable by Senior Op). See flow 15.

10. **Decision point — availability recheck on submit.** Server re-validates date range. If conflict (another booking or expired hold consumed by another quote), submit fails with a conflict panel: shows the conflicting entity, offers "Adjust dates" / "Pick alternative villa" / "Override (admin only)".

11. **Submit.** Awaited. Single button "Create booking & request deposit". A secondary "Create booking without deposit request" (requires reason).

12. **Post-submit.** Redirect to `/bookings/:id`. Booking is in `Underway` state. Calendar transitions: any existing Hold from the quote on this villa→dates becomes `Booked` (or `On Hold — Booking` per Underway convention). Holds on the OTHER quoted villas are released. Other quote lines marked `Declined`. The quote itself goes to `Converted`. Enquiry goes to `Booked`. Deposit payment request flow (flow 6) is queued and shown as next step.

**States affected:**

| Entity | Before | After |
|---|---|---|
| Quotation | `Sent` | `Converted` |
| Quotation lines | `Sent` | One `Selected`, others `Declined` |
| Enquiry | `Quoted` | `Booked` |
| Booking | — | `Underway` |
| VillaCalendar (chosen) | `On Hold` or `Available` | `Booked-Provisional` (until deposit) |
| VillaCalendar (other quoted) | `On Hold` | `Available` |
| Deposit payment | — | `Awaiting` |
| Balance payment | — | `Scheduled` with due date |
| Security deposit payment | — | `Awaiting SD details` if applicable |

**Side effects:**
- Deposit-request email queued (preview before send — flow 6).
- Owner notification (if owner has `notify_on_new_booking` flag).
- Holds on declined villas released.
- Audit log entries per state transition.

**Failure & recovery:**
- Availability conflict at submit → conflict resolution panel (above).
- Price computation mismatch (rate card changed between quote and convert) → warning banner, "Use quoted price (locked)" vs "Use current price" choice.

**Permissions:** Operator+. Owner pre-approval override requires Senior Op or Admin.

**Departures from original:** (a) Conflict resolution panel instead of generic error. (b) Payer-different-from-guest as a top-level toggle, not a hidden field. (c) Concierge tier picked at conversion (was deferred). (d) Single-form conversion rather than the original multi-page wizard. (e) Other quote lines auto-decline (was manual).

---

## 4. Direct Booking Creation (No Enquiry / Quote)

**Entry points:**
- Global "+" → "New booking" (`/bookings/new`)
- Property detail page → "Book these dates" with date range pre-filled (deep link `/bookings/new?property=:id&from=...&to=...`)
- Calendar cell context menu → "Create booking"
- Cmd-K → "New booking"

**Steps:**

1. **Screen: Direct Booking form, full page.** Same structure as flow 3 except the top section is editable: villa picker (search-as-you-type, recently-viewed first), dates (date-range picker with availability shaded), party size.

2. **Live availability + price.** As villa and dates change, an inline strip shows "Available ✓ — £4,200 for 7 nights" (or "Conflict on Aug 14 — already booked", linkable). Price breakdown popover. If villa rate card incomplete, prompt for manual price.

3. **Guest section.** Search existing contact OR create new. Same pattern as flow 1's duplicate detection.

4. **Rest of form.** Identical to flow 3 from "Section: Money" onward.

5. **Submit.** Awaited. Server re-validates. Booking created `Underway`.

**States affected:** Same as flow 3 minus the quotation/enquiry transitions. A skeleton enquiry record is **not** created (deliberate — see departures).

**Side effects:** Same as flow 3 minus the quote-line declines.

**Failure & recovery:** Same conflict panel as flow 3.

**Permissions:** Operator+.

**Departures from original:** (a) The original Blazor flow created shadow enquiry+quote records for audit; we don't — we tag the booking `origin=direct` and store the operator + reason. Cleaner. (b) Calendar-cell-driven creation is new. (c) Live price-as-you-type rather than a "Calculate" button.

---

## 5. Modify an Existing Booking

**Entry points:**
- Booking detail page → "Edit" or per-section "..." menu.
- Calendar drag of a booked range (see flow 10).
- Guest-replies-asking-to-change drawer with "Modify booking" CTA.

**Permission and editability by state — single reference table:**

| Field group | `Underway` | `DepositPaid` | `Confirmed` | `Completed` | `Cancelled` |
|---|---|---|---|---|---|
| Dates | Free edit | Edit with availability recheck + re-price | Senior Op + re-price + email guest | Locked | Locked |
| Villa | Free edit | Senior Op + full re-quote | Admin only + full re-quote + refund/charge delta | Locked | Locked |
| Party size | Free edit | Edit (may trigger occupancy band re-price) | Edit (may trigger re-price) | Edit (records only) | Locked |
| Rental price | Free edit | Senior Op (delta becomes adjustment line) | Senior Op | Locked | Locked |
| Deposit % / amount | Free edit | Locked (already paid) | Locked | Locked | Locked |
| Security deposit | Free edit | Edit if not yet held | Edit if not yet held | Edit refund only | Locked |
| Concierge | Free edit | Free edit | Free edit | Free edit (post-stay add) | Locked |
| Notes | Always editable | | | | |
| Cancel | Free (no refund) | Refund per policy | Refund per policy | Operator + Admin | — |

**Steps (date change as the canonical example):**

1. **Trigger.** Click "Edit dates" on booking. Opens an inline form with arrival/departure pickers, availability shaded behind for that villa.

2. **Live recheck.** As dates change, the system shows the new price computed from rate cards, the delta vs current booking price, and any availability conflicts.

3. **Decision point — pricing delta.**
   - Delta = 0 (rare): submit straight through.
   - Delta < 0 (cheaper): operator chooses "Adjust rental price" or "Keep current, treat as discount" (becomes a discount line, requires reason).
   - Delta > 0 (more expensive): operator chooses "Increase rental price" (then balance auto-increases, deposit either stays paid or top-up requested) or "Absorb (no extra charge)" with reason.

4. **Decision point — deposit consequences.** If booking is `DepositPaid` and rental went down, surfaces "Refund overpayment £X" with refund flow (flow 17) link OR "Apply credit to balance".

5. **Decision point — owner notification.** If villa has `notify_on_booking_change`, banner: "Owner will be notified after save."

6. **Decision point — guest notification.** Checkbox "Email guest about this change" (default on for confirmed bookings, off for `Underway`). Preview email before send.

7. **Concurrency.** If another operator edited the booking after this form loaded, save returns 409 with a diff modal: "Sara changed the deposit amount 3 minutes ago. Keep yours / keep theirs / show diff and let me choose field by field."

8. **Submit.** Awaited. State transitions per the table above; booking timeline gets a change-log entry with before/after diff.

**Cancel as a sub-flow:** "Cancel booking" button at the bottom of the edit screen — leads to flow 16.

**Villa change sub-flow:** Special — opens a "Re-quote within booking" mode that's effectively flow 2's villa search inline, but pricing carries over deposit-paid amounts and computes refund/charge deltas. Requires Senior Op.

**States affected:** Depends on field; always logs a `BookingChange` audit row with diff.

**Side effects:**
- Optional guest email.
- Optional owner notification.
- Calendar adjusts (release old range, claim new).
- Payment schedule recomputed if balance date moved due to new arrival.

**Failure & recovery:**
- Availability conflict on new dates → conflict panel (alternative dates suggestion, alternative villas suggestion).
- Refund processor error → flow 17's recovery.

**Permissions:** Per the table.

**Departures from original:** (a) Explicit editability table by state, surfaced in UI (greyed fields show a tooltip "Locked because deposit paid — Senior Op required"). (b) Concurrency diff modal. (c) Refund/credit/absorb choices presented as a tri-state decision instead of buried in a "Notes" field. (d) Change-log timeline visible to operators on the booking.

---

## 6. Take a Deposit Payment

**Entry points:**
- Booking detail → Payments panel → "Take deposit" CTA (visible when deposit state is `Awaiting`).
- Deposit-request email reply triage drawer.
- Cmd-K → "Booking VC12345 deposit".

**Steps:**

1. **Screen: Deposit panel, drawer or panel within booking page.** Shows deposit amount, due date, current state. Two large action cards:
   - **Send payment link** (online card capture)
   - **Record offline payment** (BT received)

2. **Path A: Send payment link.**
   1. Click "Send payment link". Modal: "Send to {{guest.email}} — preview".
   2. Preview email with payment link. Editable.
   3. Submit → deposit state `Sent`, email logged, link gets a token + expiry (default 7 days, configurable).
   4. Booking timeline: "Deposit link sent — expires Mar 15".
   5. Polling: deposit-panel shows live status (Sent → Viewed → Paid / Failed). When guest pays, webhook from processor lands → state `Paid`.
   6. On `Paid`: calendar transitions `Booked-Provisional` → `Booked`. Booking state → `DepositPaid`. Confirmation email queued (preview-confirmed) to guest + owner notification. Balance payment becomes the next action card.

3. **Path B: Record offline payment.**
   1. Click "Record offline". Inline form: payment method (BT, cheque, cash, other), amount (defaults to deposit amount, must reconcile or be flagged), reference, received date, file upload (bank slip).
   2. Submit awaited → state `Paid`. Same downstream as Path A.

4. **Decision point — partial payment.** If recorded amount < deposit amount, system flags "Partial — outstanding £X". State becomes `PartiallyPaid`. Calendar does NOT transition. Booking remains `Underway`. Banner: "Awaiting remainder".

5. **Decision point — overpayment.** Amount > deposit. Operator chooses "Apply excess to balance" (preferred) or "Refund excess".

6. **Decision point — booking requires owner pre-approval.** If yes (flow 15), deposit `Paid` transitions calendar to `Booked-PendingApproval`, NOT `Booked`. Booking state → `DepositPaid-PendingApproval`. Owner notification fires.

**States affected:**

| Entity | Before | After |
|---|---|---|
| Deposit payment | `Awaiting` | `Sent` (Path A) or `Paid` (Path B or A-completed) |
| Booking | `Underway` | `DepositPaid` (or `DepositPaid-PendingApproval`) |
| VillaCalendar | `Booked-Provisional` | `Booked` (or `Booked-PendingApproval`) |

**Side effects:**
- Payment link email (Path A).
- Booking confirmation email on `Paid` (preview-confirmed).
- Owner notification on `Paid`.
- Webhook handlers update state from processor events.
- Accounting export queued.

**Failure & recovery:**
- Card declined → state `Failed`, "Retry" CTA, "Send new link" CTA, operator can chase guest.
- Webhook delayed → manual "Reconcile" button polls processor.
- Calendar transition conflict (race: another booking grabbed the dates between Underway and DepositPaid) → emergency banner, escalate to admin, deposit refund initiated.

**Permissions:** Operator+. Record offline payment ≥ £10k requires Senior Op (anti-fraud).

**Departures from original:** (a) Email preview before send. (b) Partial / overpayment as first-class branches. (c) Live polling on the link status (was static). (d) Calendar two-stage transition (`Booked-Provisional` → `Booked`) to avoid the original double-booking race.

---

## 7. Manage the Rental Balance Payment

**Entry points:**
- Booking detail → Payments panel → balance card.
- Auto-reminder dashboard view (a list of all bookings with balance due in next N days).

**Steps:**

1. **Screen: balance panel.** Shows amount, due date, state. State machine identical in shape to deposit but with auto-reminders.

2. **Auto-reminder schedule.** Configured per site (e.g., 60 days before, 45, 30, 14, 7, 3, 1, day-of, overdue +3, overdue +7). Each reminder is a queued email job. The panel shows the schedule with next-reminder timestamp and a "Skip next" / "Send now" / "Pause reminders" controls.

3. **Send / record paths.** Same as flow 6.

4. **State transitions.** `Scheduled` → (auto) `Reminded` (each reminder bumps a counter, not the state) → `Sent` (when operator triggers payment link) → `Paid` / `Failed`. Plus `Overdue` flag (boolean) when past due_date and not Paid.

5. **Decision point — overdue.** When state becomes `Overdue`, a red banner appears on the booking, a row appears on operator dashboard, and an escalation email fires to a configured ops address. Booking is NOT auto-cancelled; operator decides.

6. **Decision point — guest requests extension.** Operator clicks "Change due date" — requires reason, optional new reminder schedule, logs change.

**States affected:** Balance payment state machine. Booking state advances to `Confirmed` when balance is `Paid` (subject to security deposit being also settled per site policy).

**Side effects:**
- Reminder emails (auto, but each previewable in a draft state if "human-review reminders" flag set per site).
- Overdue escalation email.
- Final confirmation email on full payment (preview-confirmed).
- Owner notification on `Confirmed`.

**Failure & recovery:** Same as flow 6.

**Permissions:** Operator+ for routine; due-date change requires Senior Op.

**Departures from original:** (a) Visible reminder schedule with skip/send/pause UI (was a black box). (b) Overdue as a flag not a state (allows `Sent` + `Overdue` simultaneously, which is more accurate). (c) Dashboard of upcoming balances.

---

## 8. Manage Security Deposit

**Entry points:**
- Booking detail → Payments panel → security deposit card.

**Steps:**

1. **Screen: SD panel.** Top of panel: SD type selector (set at booking creation but editable in flow 5 bounds) — "Pre-auth hold" / "BT refundable" / "None".

2. **Path A: Pre-auth hold.**
   1. State machine: `Awaiting SD details` → operator clicks "Send pre-auth link" → guest enters card details → `Pre-authed` (held but not captured) → after departure (manual operator action OR auto N days after departure) → "Release" (no charge, hold drops) OR "Capture X for damages" (partial capture, remainder released, requires reason + photos upload).
   2. State after release: `Released`. After capture: `Captured` with amount.

3. **Path B: BT refundable.**
   1. State: `Awaiting BT` → operator records receipt (similar form to flow 6 offline path) → `Held`.
   2. After departure: operator clicks "Refund SD" → flow 17 with amount defaulted to held amount, deductions possible (reason + photos) → `Refunded` or `PartiallyRefunded`.

4. **Path C: None.** Panel collapsed, no actions.

5. **Decision point — damages claim.** If captures/deductions, a "Damages report" sub-form: free text description, photo upload, amount itemized, optional invoice attachments (e.g., repair quote). This report is part of the audit log and is sent to the guest with the partial refund / capture email.

6. **Decision point — pre-auth expiry.** Card pre-auths expire (typically 7-30 days depending on processor). Panel shows countdown. Auto-refresh pre-auth N days before expiry if guest hasn't yet stayed.

**States affected:** SD payment state machine.

**Side effects:**
- Pre-auth via processor.
- Capture / release via processor.
- Refund via processor or offline marker.
- Damages-claim email to guest.
- Owner notification if damages > threshold.

**Failure & recovery:**
- Pre-auth fails (card declined) → state `Failed`, guest emailed to update card.
- Pre-auth expiry passed without renewal → state `Expired`, ops alerted, manual decision (re-request from guest, or accept risk).
- Refund processor error → flow 17 recovery.

**Permissions:** Operator+ for routine; damages capture > £500 requires Senior Op + photos; > £2000 requires Admin.

**Departures from original:** (a) Three explicit paths instead of one shared form. (b) Damages report as first-class entity with photos. (c) Pre-auth expiry countdown + auto-refresh. (d) Itemised deductions vs single-line.

---

## 9. Add and Charge Concierge Services

**Entry points:**
- Booking detail → Concierge panel → "Add service".
- Pre-arrival prep checklist (a derived view showing all upcoming bookings with no concierge yet).

**Steps:**

1. **Screen: Concierge panel.** Shows tier (Quintessential / Signature). If Quintessential, "Upgrade to Signature" CTA. If Signature, list of line items with state per item.

2. **Add line item.** Inline expanding row at the bottom of the list. Fields: service type (from taxonomy: airport transfer, chef, grocery, excursion, etc., or "Custom"), description (rich text), currency (defaults to booking currency, switchable), price, supplier (optional, from contact directory), supplier cost (optional, internal-only — drives margin reporting), payment timing ("Charge now" / "Charge with balance" / "Charge on completion" / "No charge (included)").

3. **Save line item.** Optimistic — appears in list immediately. Each line has its own state machine identical to deposit's: `Awaiting` → `Sent` → `Paid` / `Failed`. Or `Included` (no charge).

4. **Charge actions.** Per line: "Send payment link" / "Record offline" — same modals as flow 6. Or, batch action: "Charge all unpaid concierge" — single payment link covering multiple lines (one payment intent, line items detailed in description; on success, all linked lines transition to `Paid`).

5. **Decision point — currency mismatch.** If multiple lines in different currencies and operator triggers batch charge, system either (a) groups by currency into multiple links or (b) converts to booking currency at current FX with explicit display. Default (a), toggle for (b).

6. **Decision point — post-stay add.** Adding a line item after `Completed` is allowed but flagged "Post-stay charge — confirm intent". Useful for incidental charges.

7. **Cancel/refund line.** Cancellation pre-payment is free. Post-payment routes to flow 17.

**States affected:** ConciergeLineItem state. Booking aggregate `concierge_total` updated.

**Side effects:**
- Per-line payment link emails (preview-confirmed).
- Supplier notifications (optional, if supplier is in contact directory with `notify_on_concierge_request`).
- Margin reports.

**Failure & recovery:** Same as flow 6 per line.

**Permissions:** Operator+. Setting a line to `Included` (free) with non-zero supplier cost — i.e., a comp — requires Senior Op (margin protection).

**Departures from original:** (a) Per-line state vs single booking-wide state. (b) Batch charge across lines. (c) Supplier cost / margin tracking (was operator-spreadsheet). (d) Currency-per-line.

---

## 10. Update Villa Availability

**Entry points:**
- Property detail → Calendar tab (`/properties/:id/calendar`).
- Multi-villa timeline → click villa name (flow 11).
- Booking-related calendar transitions (flows 3, 6, 16) bypass this UI.

**Steps:**

1. **Screen: Villa Calendar, full page.** Top: month/quarter/year switcher, jump-to-date, year navigation, density toggle (compact / comfortable). Main: grid of dates, each cell colored by state and split top-half / bottom-half for changeover days. Right rail: legend, selected-range info, action buttons.

2. **Cell states:**
   - Available (white/light)
   - On Hold (yellow, with expiry tooltip and countdown)
   - Booked (green, with guest name on hover, click → booking drawer)
   - Booked-VC (darker green — booked by another VC site sharing inventory)
   - Booked-Provisional (green hatched — deposit unpaid)
   - Booked-PendingApproval (green dotted — owner approval pending)
   - Unavailable — Owner Stay (purple)
   - Unavailable — Maintenance (grey diagonal)
   - Available-Enquire (white with "?" — operator confirmation required before quote/book)

3. **Selecting a range.** Click and drag, or click first cell + shift-click last. Selected range shows summary in right rail.

4. **Setting state.** Right rail "Set state" dropdown: pick state, fill in details (notes, expiry for holds, owner-stay party detail for owner blocks). Confirm. Awaited.

5. **Half-day changeovers.** Cells have a "split" toggle (morning/afternoon). Operator can mark "Morning available, afternoon booked" for changeover days. Bookings created via flows 3/4 default to half-day arrival/departure per villa setting.

6. **Hold auto-expiry.** Holds set in this UI default to 48h. Right-rail allows custom expiry. A background job releases expired holds → `Available`, with a log entry. Operators get a daily digest of expirations.

7. **Bulk operations (right-rail expandable section):**
   - "Close season" — set a long date range to `Unavailable` with a reason taxonomy (e.g., "Winter closure").
   - "Transfer hold to booking" — convert an `On Hold` range to `Booked` by linking to / creating a booking (deep-links flow 4 with dates pre-filled).
   - "Block weekends only" — pattern-based bulk set.
   - "Mirror from another villa" — copy availability pattern (for villas with shared owner).

8. **Decision point — overwriting a booking.** Setting a `Booked` cell to anything else requires confirmation ("This will sever cell from booking VC12345 — proceed?") and is logged. Admin only.

9. **Conflict detection.** If operator tries to set `Booked-Manual` on a range that overlaps an existing booking, blocked with conflict info.

**States affected:** VillaCalendar cells.

**Side effects:**
- Owner notification if `notify_on_availability_change` flag set (debounced to one digest per N minutes).
- Site-feed cache invalidation (front-end search will see updates within seconds).
- Channel-manager push if external integration wired (Airbnb, Booking.com).

**Failure & recovery:**
- Concurrent edit by another operator → 409 → diff modal showing competing changes.
- External channel push failure → calendar updates locally, retry queue surfaces in admin panel.

**Permissions:** Operator+. Severing a booked cell requires Admin. Bulk close-season requires Senior Op.

**Departures from original:** (a) Drag-to-select range (was click-each-cell). (b) Half-day toggle as first-class UI. (c) Bulk operations panel. (d) Mirror-from-another-villa. (e) Hold expiry countdown visible. (f) Owner notifications debounced (was one email per cell change — abusive).

---

## 11. Multi-Villa Timeline View

**Entry points:**
- Main nav "Timeline" (`/timeline`).
- Region/group detail → "Timeline of these properties".
- Cmd-K → "Timeline".

**Steps:**

1. **Screen: Timeline, full page.** Top filter bar: region multi-select, site, feature filter, party-size filter, date range, sort (name / occupancy % desc / region). Below: gantt-style rows, one per villa, with horizontal axis = dates. Each row shows colored bars for bookings (green), holds (yellow), unavailables (grey/purple).

2. **Interaction.**
   - Click bar → booking drawer (flow 5).
   - Click empty area → "Create booking" with property + dates pre-filled (deep links flow 4).
   - Drag a booking bar end → "Modify dates" (flow 5).
   - Hover → tooltip (guest, party size, total).

3. **Density / zoom.** Pinch / +/− zoom from week-grain to month-grain to quarter-grain. Compact rows show only color; comfortable rows show guest initials in bar.

4. **Highlights.** A "Show gaps ≥ N nights" toggle highlights empty space between bookings — useful for filling short gaps. A "Show changeovers" toggle highlights same-day arrivals/departures (cleaning crew planning).

5. **Filters persist** in URL for sharable views.

**States affected:** None — read-only view. Drag-to-modify edits route through flow 5.

**Side effects:** None.

**Failure & recovery:** Read-only; reload on error.

**Permissions:** Operator+ (can drag-edit subject to flow 5 permissions); Viewer (read-only).

**Departures from original:** (a) Drag bars to modify (was view-only). (b) Gap highlighting. (c) Cmd-K integration. (d) URL-shareable filtered views. (e) Single timeline across regions (original was per-region).

---

## 12. Property Onboarding (Admin)

**Entry points:**
- Admin → Properties → "Add property" (`/admin/properties/new`).
- Cmd-K → "New property".

**Recommendation:** Stepwise wizard with **save-draft-at-each-step**, but each step is also reachable directly via URL so an operator can return to a half-finished property and jump to the gap. Top of every step a progress strip and "Save & exit" button. Status `Draft` until publish step.

**Steps:**

1. **Step 1 — Basics.** Internal code, public slug, name, short tagline, long description (rich text), site assignment (multi-site picker), default currency, listing status (Active draft / Active published / Archived). Save advances to step 2 URL: `/admin/properties/:id/onboard/2-location`.

2. **Step 2 — Location.** Country, region (dependent dropdown), nearest town, address (street through postcode), map pin (Mapbox / Leaflet pick), nearest airports (multi with drive-time), GPS for guest pack.

3. **Step 3 — Rooms & sleeping.** Bedrooms with per-room bed configs (king/queen/twin/sofa), max adults, max children, max infants, extra-bed availability, cots, child-safety taxonomy. Visual room cards, drag-to-reorder. Sleeping summary auto-computed for listing.

4. **Step 4 — Features.** Taxonomy chips (Pool / Sea view / etc.) plus custom feature builder. Distance to amenities (beach, town, restaurant). Accessibility flags.

5. **Step 5 — Pricing seasons.** Deferred — separate sub-flow (flow 13). The step shows "Set up seasons" CTA and a "Skip — set later" option. Property cannot publish without at least one season covering the current/next 12 months.

6. **Step 6 — Contacts & ownership.** Add contacts with role presets (Owner / Manager / Agent / Accountant / Viewer). Each contact: name, email, phone, role, override toggles for permissions (access info / availability / rates / bookings / confirm-auth / slip) and notifications (info / availability / rate / new booking / confirm req / slip). Default role-preset values are populated and surfaced with "Customise" affordance — collapsed by default per departures.

7. **Step 7 — Images.** Drag-and-drop multi-upload, reorder, set hero, alt text per image, caption, categorisation (Exterior / Interior / Bedroom / etc.), publish/unpublish per image.

8. **Step 8 — Policies.** Deposit %, balance due days, security deposit type + amount, cancellation policy template (picked from a managed list, overridable per property), house rules, check-in/out times, concierge default tier.

9. **Step 9 — Publish.** Pre-flight checklist showing all required fields, all warnings, "Publish" awaited button. Status → `Active published`.

**Decision points:**
- Skip pricing — property remains `Draft`, cannot accept bookings.
- Skip images — warning, property publishable but discouraged.
- Address geocoding fails — manual pin placement.

**States affected:** Property aggregate plus Season / RateCard / Contact / Image / Calendar entities.

**Side effects:**
- Empty calendar generated with default "Available" for next 24 months.
- Search index updated.
- Notification to ops team.
- Owner welcome email if Owner contact added.

**Failure & recovery:** Each step save is atomic; failures don't lose previous steps.

**Permissions:** Admin only for create / publish; Senior Op can edit Draft.

**Departures from original:** (a) Stepwise but with deep links per step (was monolithic page). (b) Save drafts at each step (was all-or-nothing). (c) Role presets for contacts collapse the permission matrix (massive UX win). (d) Pre-flight checklist before publish. (e) Map-pin location (was lat/long fields).

---

## 13. Set Up a Season + Rate Cards

**Entry points:**
- From property onboarding step 5.
- From property detail → Pricing tab.
- Bulk: Admin → Pricing → "New season" (multi-property apply).

**Recommendation on form structure:** Two-level form — Season at the top (one record), then RateCard rows nested inside (N records). Each RateCard row is collapsible, with a "preview computed price" affordance showing what a sample 7-night stay would cost under that card, so the operator can sanity-check the matrix without leaving the form.

**Steps:**

1. **Screen: Season form, full page.**

2. **Season fields.** Name (e.g., "Summer 2026"), start date, end date, currency, status (Active / Draft / Archived), notes.

3. **RateCard rows.** Inside the season, an empty row + "Add rate card" button. Each row collapses to a one-line summary; expanded form:
   - Date sub-range (must be within season dates) — supports multiple disjoint ranges per card (operator's choice if simpler to have one card cover both halves of a split mid-season).
   - Pricing mode: Nightly / Weekly / Custom-tiered (e.g., 7 nights £X, 10 nights £Y).
   - Base price.
   - Commission % (paid to VC).
   - Tax % (and inclusive/exclusive toggle).
   - Occupancy bands: a table — for each occupancy count (or range), an override price or a multiplier. Default: party size doesn't affect price.
   - Discount rules: early-bird (% off if booked > N days out), last-minute (% off if booked < N days out, with floor), length-of-stay tiers, repeat-guest discount.
   - Extras: cleaning fee (per stay / per night), pet fee, heating fee (seasonal), extra-bed fee, linen, optional add-ons.
   - Min nights / max nights, changeover-day restriction (e.g., Saturday-only).

4. **Preview pane (right rail).** Sticky. Date pickers + party-size + occupancy-count → preview computes a quote: nightly breakdown, applied card, applied discount, extras, total. Recomputes on every change. Helps operator catch errors before save.

5. **Decision point — overlapping ranges.** If two rate cards' date sub-ranges overlap, form blocks save with conflict highlight. Operator must split or merge.

6. **Decision point — gaps.** If rate cards leave nights within the season uncovered, warning (not blocking — uncovered nights fall back to "manual quote required").

7. **Save.** Awaited.

8. **Bulk apply (admin path).** A toggle "Apply to multiple properties": property picker, identical season created on each, identical rate cards. With option to scale prices (+/- % per property).

**States affected:** Season + RateCard entities. Quotation pricing for in-flight quotes is NOT retroactively updated (those use locked prices); new quotes use new rates.

**Side effects:**
- Search-listing price displays refresh.
- Channel manager push (rate updates) if external integration wired.
- Owner notification if `notify_on_rate_change` (one digest, not per-card).

**Failure & recovery:** Standard form validation.

**Permissions:** Admin to create / edit / archive; Senior Op can read; Operator read-only.

**Departures from original:** (a) Two-level form with collapsible rate-card rows (was a flat sheet that scrolled forever). (b) Live preview pane. (c) Overlap detection up-front. (d) Bulk apply with price scaling. (e) Gap warning (uncovered nights). (f) Occupancy bands as a table not free-form text.

---

## 14. Owner Portal — View Bookings & Payouts

**Entry points:**
- Owner logs in at `/owner/login` → redirected to `/owner` dashboard.
- Owner notification email link → deep links into specific booking or statement.

**Steps:**

1. **Screen: Owner dashboard.** Top cards: properties count, upcoming arrivals (next 30 days), occupancy % YTD, gross revenue YTD, net payout YTD. Below: tabs — Properties / Bookings / Statements / Notifications / Profile.

2. **Properties tab.** List of owner's properties. Each: hero image, name, occupancy bar, this-month bookings count, "View calendar" link.

3. **Property → calendar.** Read-only version of flow 10. Owner sees Booked / Hold / Unavailable but with guest detail redacted by default (initials only). "Show guest details" toggle if owner has `view_guest_details` permission. Owner can request blocks (flow 10 owner-stay path) which create a "Pending owner block" that an operator approves.

4. **Bookings tab.** Per-booking row with date / guest initial / party size / rental / net to owner / status. Click → booking drawer (owner-view variant: redacted financial detail unless `view_full_money` permission, no internal notes).

5. **Statements tab.** Per-month statements list. Click a month → statement detail: header (owner / property / period), gross bookings table, fee deductions (commission, tax remittance, repairs charged back, etc.), net payout, payout status (Pending / Paid with reference). PDF download. CSV download for accountants.

6. **Notifications tab.** Toggle each notification flag per property (info change / availability change / rate change / new booking / confirm request / slip). Granular per property because owners with multiple villas often want different settings.

7. **Profile tab.** Contact details, password/MFA, language, payout bank details (KYC-gated).

**Decision points:**
- Owner requests block (date range) → operator notification → flow 10 approval.
- Owner clicks "Approve" on pending-approval booking → flow 15.

**States affected:** OwnerBlockRequest / NotificationPreferences. Read-only for everything else.

**Side effects:**
- Operator notification on owner-initiated block request.
- Audit log entry on every owner action (regulatory).

**Failure & recovery:** Standard.

**Permissions:** Owner role + property-scoped permission flags.

**Departures from original:** (a) Single dashboard rather than the original "Owner Area" frames. (b) Per-property notification settings (was global per owner). (c) PDF + CSV statements (was PDF only). (d) Owner-initiated block requests (was email-the-ops-team). (e) Redacted-by-default guest info (GDPR).

---

## 15. Approve a Booking Requiring Owner Pre-Approval

**Entry points:**
- Owner email "New booking awaiting your approval" → link.
- Owner portal → notifications / bookings list with "Action required" badge.
- Operator dashboard surfaces pending-approval bookings too (with escalation if owner hasn't responded in N days).

**Steps:**

1. **Screen: Booking detail (owner view) with action bar at top.** "Approve" / "Decline (with reason)" / "Request more info".

2. **Approve.** Awaited. Booking state `DepositPaid-PendingApproval` → `DepositPaid`. Calendar `Booked-PendingApproval` → `Booked`. Confirmation emails fire (guest + operator).

3. **Decline.** Modal: reason (taxonomy: "Owner using property" / "Concerns about party" / "Other"), free-text comments. Awaited. Booking state → `Cancelled-OwnerDeclined`. Deposit auto-refund initiated (flow 17). Calendar releases. Guest email with apology + offer to rebook elsewhere.

4. **Request more info.** Free-text message to operator (not directly to guest). Booking state unchanged (still pending). Operator notified. Owner timeline shows the question and operator's response when given.

5. **Decision point — timeout.** If owner doesn't respond within site-configured window (default 48h), escalation: operator alerted, optional auto-approval if site policy allows.

**States affected:**

| Entity | Before | After (approve) | After (decline) |
|---|---|---|---|
| Booking | `DepositPaid-PendingApproval` | `DepositPaid` | `Cancelled-OwnerDeclined` |
| VillaCalendar | `Booked-PendingApproval` | `Booked` | `Available` |
| Deposit | `Paid` | `Paid` | `Refunding` → `Refunded` |

**Side effects:**
- Guest confirmation email (approve) or apology+refund email (decline).
- Operator notifications.
- Audit log.

**Failure & recovery:**
- Refund processor error on decline → flow 17 recovery.
- Owner accidentally declines → "Undo" available for 5 minutes before refund triggers (departure).

**Permissions:** Owner / Manager (if property has manager-approval delegation).

**Departures from original:** (a) "Undo" buffer on decline before refund triggers. (b) "Request more info" path (was decline-or-approve binary). (c) Escalation/auto-approval on timeout. (d) Dual visibility in both owner portal AND operator dashboard.

---

## 16. Cancel a Booking

**Entry points:**
- Booking detail → "Cancel booking" (footer of edit screen, flow 5).
- Owner decline (flow 15).
- Guest-initiated via reply to ops, recorded by operator.

**Steps:**

1. **Screen: Cancellation modal.**

2. **Reason taxonomy.** Guest-initiated (sub: change of plans, medical, force majeure, found alternative, complaint) / Operator-initiated (sub: villa unavailable, owner declined, fraud, other) / Owner-initiated. Free-text required.

3. **Policy computation.** System computes refund per cancellation policy applied to the booking. Sliding scale based on days-from-arrival and amounts paid:
   - Pre-deposit: free, no refund needed (nothing paid).
   - Post-deposit, > N days from arrival: refund deposit minus admin fee.
   - Post-deposit, < N days: deposit forfeit.
   - Post-balance, > M days: full refund minus admin fee.
   - Post-balance, < M days: sliding scale (e.g., 50% / 25% / 0%).
   - Force majeure: full refund regardless (operator override with reason).

4. **Refund preview.** Itemized table: amounts paid, policy refund %, computed refunds per payment stream (deposit / balance / SD / concierge), total refund, total retained.

5. **Override controls.** Senior Op can adjust per-line refund amounts with reason. Admin can override anything.

6. **Decision point — security deposit.** If SD was pre-authed but not captured, release automatically. If BT-held, refund.

7. **Decision point — concierge with completed services.** Concierge line items already `Paid` for services not yet rendered → refund. Already-rendered services → no refund.

8. **Decision point — re-bookable inventory.** If cancel is > N days out and high-demand, banner: "These dates are likely re-bookable — consider holding the deposit as credit instead of refund." Operator can offer credit.

9. **Confirm.** Awaited. Booking state → `Cancelled` (with sub-state for reason category). Refund flow (flow 17) triggered for each payment stream. Calendar releases (`Booked` → `Available`). Owner notification. Guest cancellation email (preview-confirmed) with itemized refund.

**States affected:**

| Entity | Before | After |
|---|---|---|
| Booking | (any active state) | `Cancelled` |
| VillaCalendar | `Booked*` | `Available` |
| Each payment stream | various | `Refunding` → `Refunded` (or no-op) |

**Side effects:**
- Multiple refund processor calls.
- Guest cancellation email.
- Owner cancellation notification.
- Re-marketing trigger (the now-free dates surface in any saved-searches-for-this-period subscriptions).
- Accounting export.

**Failure & recovery:**
- Refund failure → see flow 17.
- Calendar release race (another operator quoted during cancel) → no conflict because nothing was holding the dates, but new quote inherits availability.

**Permissions:** Operator+ for routine cancels per policy. Override per-line refund requires Senior Op. Force majeure full refund requires Senior Op. Cancel a `Completed` booking (rare, e.g., dispute) requires Admin.

**Departures from original:** (a) Itemised refund preview per payment stream. (b) Credit-instead-of-refund affordance for in-demand dates. (c) Reason taxonomy. (d) Re-marketing trigger. (e) Senior-Op override audit.

---

## 17. Refund Flow

**Entry points:**
- Triggered by flow 5 (overpayment refund), flow 8 (SD refund), flow 15 (owner decline), flow 16 (cancellation), flow 9 (concierge refund).
- Direct: operator on booking → Payments panel → "Refund" on a paid line.

**Steps:**

1. **Screen: Refund modal (or panel embedded in caller flow).**

2. **Refund amount.** Defaulted by caller flow (policy-computed or full). Editable subject to permission. Currency matches the original payment.

3. **Refund target.** Original payment method (for online card payments, refund to card). For BT-collected, operator captures bank details (or uses stored owner-bank-details for owner-side refunds).

4. **Method.** Online (processor refund) / Offline (mark refund issued, attach reference, e.g., BT confirmation).

5. **Reason.** Free text plus taxonomy.

6. **Confirm.** Awaited. Processor call issued (online) or marker created (offline). State `Refunding` → `Refunded` on processor success.

7. **Partial refund.** Sub-state `PartiallyRefunded`. Multiple partial refunds can stack against a single payment (each tracked as its own RefundEvent).

**States affected:** Payment state machine — `Paid` → `Refunding` → `Refunded` / `PartiallyRefunded` / `RefundFailed`.

**Side effects:**
- Processor refund API call.
- Refund confirmation email to guest (preview-confirmed for non-emergency; auto-fired for cancellation chains with template).
- Accounting export.
- Audit log.

**Failure & recovery:**
- Processor declines (e.g., card closed, refund window exceeded) → state `RefundFailed`, banner with options: "Retry with different method" / "Issue BT refund" (manual offline marker after operator processes BT).
- Refund window exceeded (Flywire's gateway-side refund window — 90-180 days depending on payment method) → forced to BT-offline path.

**Permissions:** Operator+ up to £X per refund (site-configurable). Senior Op up to £Y. Admin above.

**Departures from original:** (a) Online + offline parity in one flow. (b) Partial-refund stacking with audit. (c) Window-exceeded fallback. (d) Per-line refunds (was booking-level only).

---

## 18. Run a Report / Owner Statement / Occupancy Export

**Entry points:**
- Main nav "Reports" (`/reports`).
- Owner portal → Statements (read-only).
- Property detail → "Generate statement for this property".

**Steps:**

1. **Screen: Reports hub.** Tiles per report type: Owner statements, Occupancy, Revenue / commission, Concierge margin, Refunds & cancellations, Lead funnel (enquiry → quote → booking), Operator productivity, Custom.

2. **Pick a report type → configurator.** Common controls: period (this month / last month / this quarter / YTD / custom range), scope (single property / property group / region / site / all), grouping (by property / by region / by month / by operator / by site), filters (status, currency, agent, etc.).

3. **Preview.** Inline table + chart preview (limited to first N rows). Editable column visibility, sort, etc. — like a lightweight pivot.

4. **Export.** Buttons: CSV / Excel / PDF (formatted) / Email to recipients (multi-email picker, optional message). Awaited per export.

5. **Schedule (optional).** "Run this monthly" — cron-style schedule, recipients, format. Creates a saved report.

6. **Saved reports panel.** List of recurring reports with last-run, next-run, edit, pause.

**States affected:** ReportRun audit entity.

**Side effects:**
- Email with attachment.
- Storage of PDF/CSV in a reports archive (retention per site policy).
- For scheduled reports: cron job creation.

**Failure & recovery:** Generation failure → retry, log.

**Permissions:** Operator for ops reports; Accountant for financial reports; Admin for cross-site / cross-region reports; Owner for own properties only via portal.

**Departures from original:** (a) Unified reports hub with consistent UX (originally several disparate screens). (b) Preview before export. (c) Scheduled / recurring reports. (d) Owner statements share the same engine as ops reports (consistency).

---

## 19. Bulk Operations

**Entry points:**
- Admin → Bulk operations.
- Per-context: Calendar timeline → multi-select villas → "Bulk action"; Pricing → "Bulk rate change"; Properties list → multi-select → "Bulk edit".

**Steps:**

1. **Screen: Bulk operation wizard.** Three-step: Pick scope → Configure change → Preview & confirm.

2. **Step 1 — Scope.** Filter / select properties: by region / site / tag / individual picker. Selection persists in URL.

3. **Step 2 — Configure.** Operation type:
   - **Block dates** (close season): date range, state (Unavailable / Owner Stay / Maintenance), reason, override existing bookings? (default no).
   - **Bulk rate change**: target seasons (current / specific year), change type (% increase / decrease / fixed amount), apply to (base price / commission / both), preview impact.
   - **Bulk feature toggle**: add/remove feature chips across selected villas.
   - **Bulk policy update**: deposit % / balance days / cancellation policy template.
   - **Inventory export**: CSV/Excel of all villa fields.
   - **Bulk image categorisation**: rare.

4. **Step 3 — Preview.** Table: villa | before | after, with conflicts flagged (e.g., "Villa X has 3 bookings in this range — skipped"). Operator confirms only non-conflicting changes, or chooses "Force" for conflicts (Admin only).

5. **Confirm.** Awaited, long-running. Progress bar with per-villa status. Cancellable mid-run. Partial completion allowed — every change is independently committed (no all-or-nothing).

**States affected:** Many — depends on operation. Each is logged individually as if the operator made it.

**Side effects:**
- Owner notification digest (single email per affected owner, batched).
- Search/channel manager refresh.
- Audit log entries (one per villa per change, batched in UI).

**Failure & recovery:** Per-villa retries; final summary shows X succeeded, Y failed with reasons.

**Permissions:** Admin only for cross-property bulk changes; Senior Op for bulk-within-region.

**Departures from original:** (a) Existed only as ad-hoc SQL or per-villa repetition; now first-class UI. (b) Preview-before-commit. (c) Partial completion with summary. (d) Batched owner notifications.

---

## 20. Search Everywhere (Cmd-K Command Palette)

**Entry points:**
- Cmd-K / Ctrl-K anywhere in the app.
- Top-bar search icon.
- "/" shortcut for the empty palette.

**Steps:**

1. **Screen: Modal palette over current view.** Single input + result list.

2. **Result types.** As operator types, results are grouped:
   - **Recent** — most-recently-viewed entities (top 3 always shown on empty input).
   - **Quotations** — match `QuotationNo`, guest name, email.
   - **Bookings** — match `BookingRef`, guest, payer, agent, dates.
   - **Enquiries** — match guest, email, phone.
   - **Contacts** — guests, owners, managers, agents, suppliers.
   - **Properties** — name, slug, code, region.
   - **Actions** — "New enquiry", "New booking", "Open calendar for Villa X", "Run report Y" (verb-noun phrases).
   - **Navigation** — "Go to timeline", "Go to reports", "Go to admin".

3. **Ranking.** Recently-viewed weighted up; exact-match on ref number always top.

4. **Keyboard nav.** Up/down to select, Enter to open in drawer (default) or Cmd+Enter to open in full page.

5. **Direct routing.** Typing a number like "QVC12345" or "VC67890" routes directly. Typing "?" surfaces help / shortcuts.

6. **Scoped search.** Prefix with type to scope: `b:` bookings only, `e:` enquiries, `p:` properties, `c:` contacts, `>` for actions. Example: `> new booking`.

7. **Recent searches.** Below results, last 5 queries.

**States affected:** None.

**Side effects:** Search log (for query analytics — what operators look for most, to inform UX priorities).

**Failure & recovery:** Standard.

**Permissions:** Results respect the user's permission scope — Operators see all operational entities; Owners (when palette is opened in owner portal) see only their own.

**Departures from original:** (a) Cmd-K palette is entirely new — the original had no global search. (b) Action verbs in the same surface ("New booking", "Open calendar"). (c) Scoped prefixes. (d) Recent items on empty input.

---

## Closing notes on cross-workflow themes

A few patterns recur and should be treated as first-class implementation primitives rather than per-flow code:

- **Email preview component.** Used in flows 1, 2, 3, 6, 7, 8, 9, 15, 16, 17. Single component, template-driven, with edit-and-send.
- **Conflict resolution panel.** Used in flows 3, 4, 5, 10, 16. Shared component for "what should happen when the world changed under you".
- **Payment state machine card.** Used in flows 6, 7, 8, 9. One reusable state-card with state-specific actions.
- **Preview-then-commit pattern.** Used in flows 16, 17, 18, 19. A wrapper for any destructive / financial / bulk action.
- **Concurrency diff modal.** Used wherever multiple operators edit the same entity.
- **Notification settings respect.** Owner / manager / agent flags consulted at every side-effect emission point — centralize in a notification dispatcher service.

### Source references in the original system

For domain semantics (not direct port), the canonical sources are:

- Booking edit: `/Users/garethlloyd/projects/villacollective/ResSystem/NewResSystem/Pages/Bookings/Booking.razor`
- Quotation flow: `/Users/garethlloyd/projects/villacollective/ResSystem/NewResSystem/Pages/QuotationsEnquiry/`
- Single-villa calendar: `/Users/garethlloyd/projects/villacollective/ResSystem/NewResSystem/Pages/Properties/Availability/Availability.razor` and the `AvailabilityCard.razor` component
- Booking service: `/Users/garethlloyd/projects/villacollective/ResSystem/NewResSystem.Core/Services/ResService/ResService.cs` (the ~5,200-line core)
- Pricing engine: `/Users/garethlloyd/projects/villacollective/ResSystem/NewResSystem.Core/Services/Properties/RatesModel.cs`
- Status enums + email template names: `/Users/garethlloyd/projects/villacollective/ResSystem/NewResSystem.Core/Enums.cs`
