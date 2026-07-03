# Client Emails — Mockup Analysis

> Source: https://vc-emails.netlify.app/
> Reviewed against: `django_res_design/workflows/`, `django_res_design/product-design/`
> Mockup data extracted from the inline `TEMPLATES` array in the page's React app (single-file SPA at `index.html`).

---

## 1. Summary

- The mockup catalogues **14 templates** across **5 categories**: Bookings (4), Payments (5), Communications (2), Pre-Stay (2), Post-Stay (1).
- Audience badges in the mockup: **13 templates are client-facing**, **1 is owner-facing** (Owner Approval Request). There are **no internal/ops-facing templates** in the mockup.
- Roughly **60% map cleanly to specced workflow triggers** (deposit/balance reminders, owner approval, concierge payment, booking confirmation). The remaining **~40%** are either new lifecycle-comms with no triggering workflow yet (Pre-Arrival, Check-In Reminder 48h, Post-Stay Thank You, New Message from VC, Service Request Update) or duplicate-state variants (Booking Confirmation vs. Paid-in-Full).
- **Top callouts:**
  - The catalogue **omits every email the workflows demand at the enquiry and quotation stages** (`workflows/07-enquiry/enquiry-intake.md:32-33`, `workflows/08-quotation/transmission.md:26-28`).
  - The catalogue **omits every owner-side notification except the approval request** — no owner new-booking notice, change notice, cancellation notice, or digest, despite the legacy `OWNER_BOOKING_CONFIRM` template and the recurring "owner notification" side effect in `product-design/03-workflows.md` (flows 3, 5, 6, 7, 10, 15, 16).
  - The catalogue **omits internal/ops escalations** (overdue, fraud alert, stale-hold notifications) from `product-design/03-workflows.md:365-370` and `workflows/12-automation/scheduler-jobs.md:91`.
  - The catalogue **introduces new lifecycle nudges** (Pre-Arrival 7d, Check-In 48h, Post-Stay Thank-You) that have **no specced scheduler job** in `workflows/12-automation/scheduler-jobs.md`.
  - The Communications category (Service Request Update, New Message from VC) implies a **guest-messaging primitive** that isn't in the domain model (`product-design/01-domain-model.md` has `EmailTemplate` + `EmailLog` but no `BookingMessage` / `ServiceRequest` entity).

---

## 2. Template inventory (mockup-side)

All 14 templates extracted verbatim from the `TEMPLATES` array. Audience badge is the mockup's own classification (`client` / `owner` / `internal`).

| # | Category | Mockup label | Audience | Subject (rendered against demo data `D`) |
|---|---|---|---|---|
| 0 | Bookings | Proceed to Booking | client | `Confirm Your Stay — Villa Elysian · 16th May 2026 – 23rd May 2026` |
| 1 | Bookings | Booking Confirmation | client | `Booking Confirmed — Villa Elysian · 16th May 2026 – 23rd May 2026` |
| 2 | Bookings | Booking Confirmation (Paid in Full) | client | `Booking Confirmed — Villa Elysian · 16th May 2026 – 23rd May 2026` |
| 3 | Bookings | Owner Approval Request | **owner** | `Booking Approval Required — Villa Elysian · 16th May 2026 – 23rd May 2026` |
| 4 | Payments | Balance Payment Received | client | `Balance Payment Received — Villa Elysian · Ref: VC3345` |
| 5 | Payments | Balance Reminder (7 Days) | client | `Balance Due in 7 Days — Villa Elysian · €9,940` |
| 6 | Payments | Balance Reminder (3 Days) | client | `REMINDER: Balance Due in 3 Days — Villa Elysian · €9,940` |
| 7 | Payments | Balance Due Today | client | `⚠ Balance Due Today — Villa Elysian · €9,940` |
| 8 | Payments | Concierge Payment Request | client | `Payment Request: Private Chef — 3× Dinner Service · Ref: VCX-002` |
| 9 | Communications | New Message from VC | client | `Message from Villa Collective — Villa Elysian · Ref: VC3345` |
| 10 | Communications | Service Request Update | client | `Service Update: Private Chef — 3× Dinner Service — Confirmed · Ref: VC3345` |
| 11 | Pre-Stay | Pre-Arrival Information | client | `Your Pre-Arrival Guide — Villa Elysian · Arriving 16th May 2026` |
| 12 | Pre-Stay | Check-In Reminder (48h) | client | `You arrive in 48 hours — Villa Elysian · 16th May 2026` |
| 13 | Post-Stay | Post-Stay Thank You | client | `Thank You for Staying — We Hope to Welcome You Again` |

Common CTAs (button styles, from `vcButton(...)`): primary tan `#e6b380`, success green `#2d6a4f`, danger red `#9b2335`, outline tan. Two payment routes are surfaced consistently: **Pay via Flywire** (`d.flywireUrl`) and **Pay by Card** (`d.payUrl`). The owner email exposes **Approve** (green) / **Decline** (red).

Demo merge fields exposed by `D` (mockup `index.html:60-109`):

- Booking identity: `ref`, `property`, `location`, `arrive`, `depart`, `nights`, `adults`, `children`, `checkIn`, `checkOut`.
- Guest: `clientName`, `clientFirstName`, `clientEmail`.
- Owner: `ownerName`, `ownerFirstName`, `ownerEmail`.
- Salesperson: `salesperson`, `salespersonEmail`, `salespersonPhone`.
- Gross money (guest-facing): `totalAmount`, `deposit`, `depositDate`, `balance`, `balanceDue`, `balancePaidDate`, `securityDeposit`, `securityDepositDue`.
- Net money (owner-facing): `netTotal`, `netDeposit`, `netBalance`, `commissionRate`.
- Villa content: `villaInfo`, `furtherInfo`, `serviceInclusions`.
- Action URLs: `approveUrl`, `declineUrl`, `payUrl`, `flywireUrl`, `bookingUrl`.
- Concierge / messaging: `serviceItem`, `serviceAmount`, `serviceInvoiceRef`, `serviceStatus`, `serviceDetail`, `messagePreview`.
- Misc: `holdExpiresIn`.

---

## 3. Per-template specification

### 3.0 Proceed to Booking

- **Mockup label:** "Proceed to Booking"
- **Mockup trigger (verbatim):** *"Sent to client once a quote is accepted — invites them into the secure checkout to pay the deposit and confirm the booking"*
- **Specced triggering event(s):**
  - Closest fit is **`product-design/03-workflows.md` flow 6 / "Path A: Send payment link"** (`product-design/03-workflows.md:305-311`) — the deposit-request email that fires from `/bookings/{id}/deposit:request-payment` (`product-design/04-rest-api-surface.md:522`).
  - There is **no direct legacy email** for this step — the legacy flow conflates checkout-info capture (`workflows/10-payment/checkout-flow.md` `PAYMENT.CHECKOUT.SAVE_INFO`) with the WP-hosted gateway; the "you can now pay your deposit" email does not exist as a named template in `workflows/11-integrations/email-delivery.md:107-122`.
  - Cross-reference: `product-design/03-workflows.md` flow 3 *Convert Quotation to Booking* (`:163`) — the post-submit step queues the deposit-request email.
- **Merge fields implied by the body:** `clientFirstName`, `property`, `location`, `bookingUrl`, `ref`, `arrive`, `checkIn`, `depart`, `checkOut`, `nights`, `adults`, `children`, `totalAmount`, `deposit`, `balance`, `balanceDue`, `holdExpiresIn`, `salespersonPhone`, plus the salesperson block.
- **Coverage classification:** **Covered (product-design)** — it fills the gap between "quote accepted" and "deposit paid" and is what flow 3 needs after quotation conversion.
- **Notes:**
  - The body explicitly references **30 % deposit**, which is consistent with the percent-default at booking creation (`product-design/03-workflows.md:150`).
  - References **"Booking Terms & Conditions PDF"** and the **client portal** — neither has a workflow file. The portal is implied by the Communications templates (see §5).
  - `holdExpiresIn` is shown as **"5 working days"** in `D`, but `product-design/03-workflows.md:106` and `workflows/12-automation/scheduler-jobs.md:50-64` use **7 days for `AvailableStatus=40` legacy / 48 h for `On Hold` post-quote in flow 2**. The 5-working-days value is **new and undocumented**.
  - The two-button "Bank Transfer (Flywire)" vs "Card Payment" pattern is implicit in `product-design/03-workflows.md:302` but isn't visible in the deposit endpoint shape in `product-design/04-rest-api-surface.md:522` — the API exposes a single `request-payment` action. The mockup implies the rendered link page surfaces both rails, not that there are two separate emails.

### 3.1 Booking Confirmation

- **Mockup label:** "Booking Confirmation"
- **Mockup trigger (verbatim):** *"Sent to client immediately after booking is confirmed and deposit received"*
- **Specced triggering event(s):**
  - **`workflows/10-payment/payment-collection.md` `PAYMENT.COLLECTION.WEBHOOK_RECEIVE`** step 6 (`:73-74`): on `status == "guaranteed"`, `SentEmailToPayerAndLeadGuest(bookingRefNo)`. Legacy template: `BOOKING_RECEIPT` (`workflows/11-integrations/email-delivery.md:113`).
  - **`product-design/03-workflows.md` flow 6 step 2.6** (`:311`): "Confirmation email queued (preview-confirmed) to guest + owner notification."
- **Merge fields implied:** `clientFirstName`, `property`, `location`, `ref`, `arrive`/`depart`, `checkIn`/`checkOut`, `nights`, `adults`/`children`, salesperson block, `villaInfo`, `furtherInfo`, `serviceInclusions`, `totalAmount`, `deposit`, `depositDate`, `balance`, `balanceDue`, `securityDeposit`.
- **Coverage classification:** **Covered (legacy + product-design)** — `BOOKING_RECEIPT` semantics, but enriched with the three villa-info text blocks the legacy template did not carry.
- **Notes:**
  - Surfaces the **security deposit as a separate manual BT invoice ~14 days before arrival**. This matches the legacy `SECURITY_DEPOSIT_PAYMENT` template (`workflows/11-integrations/email-delivery.md:111`) and the SD-pre-stay trigger in `workflows/12-automation/scheduler-jobs.md:36-38` (`isStayDate OR isEmailSentBeforeCD`). However, the legacy SD reminder fires only at **`balance.AddDays(-7)`** OR **`arrivalDate`**, not the **14-day window** quoted in the mockup body. This is a **new SD cadence** that the redesign should formalise.
  - `villaInfo`, `furtherInfo`, `serviceInclusions` map to `PropertyDescription` rows in `product-design/01-domain-model.md:62` (section enum: `overview` / `house_rules` / `villa_info` / `further_info`). Inclusions don't have a dedicated section enum value — see §7.

### 3.2 Booking Confirmation (Paid in Full)

- **Mockup label:** "Booking Confirmation (Paid in Full)"
- **Mockup trigger (verbatim):** *"Sent when full payment is received upfront and the booking is confirmed in a single transaction"*
- **Specced triggering event(s):**
  - **No direct workflow trigger.** The closest is **`PAYMENT.COLLECTION.WEBHOOK_RECEIVE`** (`workflows/10-payment/payment-collection.md:48-99`) with a payment whose `amount` equals `totalAmount`.
  - In `product-design/03-workflows.md` flow 6, "full" payment is **not modelled** — flow 6 is the deposit, flow 7 is the balance. A single-shot full payment is implicit at most.
  - Variant of `BOOKING_RECEIPT` (`workflows/11-integrations/email-delivery.md:113`).
- **Merge fields implied:** Same as 3.1, minus `balance` / `balanceDue` (replaced by `depositDate` rendered as "Date Paid").
- **Coverage classification:** **New / speculative** — the redesign assumes a 3-tier payment schedule (deposit / balance / SD) per `product-design/03-workflows.md:177-179`; "paid in full" is a special case that hasn't been spec'd.
- **Notes:**
  - Distinguished only by the "Payment Summary" section showing **"PAID IN FULL"** instead of split deposit/balance lines. Subject line is **identical** to 3.1, which will cause Gmail-thread merging.
  - Needs a trigger: probably `Booking.deposit_state == 'paid' AND Booking.balance_state == 'paid' on same PaymentEvent` (i.e., a single payment satisfied both tracks). Should consume a separate `EmailTemplate.key` (e.g., `booking_confirmation_paid_in_full`) per `product-design/01-domain-model.md:378-379`.

### 3.3 Owner Approval Request

- **Mockup label:** "Owner Approval Request"
- **Mockup trigger (verbatim):** *"Sent to villa owner when a new booking is pending their approval"*
- **Specced triggering event(s):**
  - **`workflows/09-booking/booking-confirmation.md` `BOOKING.LIFECYCLE.OWNER_CONFIRM`** (`:7-49`). Note the legacy flow is *staff transcribing the owner's reply* — the email-to-owner with self-service approve/decline links is **explicitly flagged as a redesign improvement** at `workflows/09-booking/booking-confirmation.md:47` ("the Django redesign could offer a self-service token-based 'approve / reject' page emailed directly to the owner").
  - **`product-design/03-workflows.md` flow 15 *Approve a Booking Requiring Owner Pre-Approval*** (`:697-735`) — the design captures the owner-portal approval surface; this email is the email that links into flow 15.
- **Merge fields implied:** `ownerFirstName` / `ownerName`, `property`, `location`, `ref`, `arrive` / `checkIn` / `depart` / `checkOut`, `nights`, `adults`, `children`, `clientName`, the three villa-info blocks, `netTotal`, `netDeposit`, `netBalance`, `commissionRate`, `securityDeposit`, `approveUrl`, `declineUrl`, salesperson block.
- **Coverage classification:** **Covered (product-design)** — explicitly described as an improvement-over-legacy in `workflows/09-booking/booking-confirmation.md:47` and surfaced in flow 15.
- **Notes:**
  - The **net figures** (`netTotal`, `netDeposit`, `netBalance`, `commissionRate`) are the only owner-side money fields surfaced anywhere in the mockup. Legacy `OWNER_BOOKING_CONFIRM` (`workflows/11-integrations/email-delivery.md:114`) presumably had this but isn't documented; in the redesign, `PropertyFinance.commission_calculation_type` + `commission_amount` (`product-design/01-domain-model.md:71`) plus `Payment.amount` derive these.
  - Body says **"Declining a confirmed booking within 30 days of arrival may be subject to our owner agreement terms"** — this is a policy statement the spec does not yet capture. `product-design/03-workflows.md` flow 15 omits any time-of-decline penalty.
  - The `approveUrl` / `declineUrl` are tokenised links — these correspond to the **`MagicLink`** entity in `product-design/01-domain-model.md:313` or an analogous owner-approval token, not yet specced.
  - Cross-reference: `product-design/03-workflows.md:714` *"timeout escalation if owner doesn't respond within site-configured window (default 48h)"* — the mockup says **"at your earliest convenience"** with no timeout cue. The redesign should add a deadline merge field.

### 3.4 Balance Payment Received

- **Mockup label:** "Balance Payment Received"
- **Mockup trigger (verbatim):** *"Sent to client when their final balance payment is confirmed"*
- **Specced triggering event(s):**
  - **`workflows/10-payment/payment-collection.md` `PAYMENT.COLLECTION.WEBHOOK_RECEIVE`** (`:73-74`) — `SentEmailToPayerAndLeadGuest(bookingRefNo)` on `status == "guaranteed"` for a payment with `description == "Rental Balance Payment"`.
  - **`product-design/03-workflows.md` flow 7 step 4** (`:363`) — `Paid` transition fires "Final confirmation email on full payment (preview-confirmed)".
- **Merge fields implied:** `clientFirstName`, `property`, `location`, `ref`, `arrive`/`depart`, `deposit`, `depositDate`, `balance`, `balancePaidDate`, `totalAmount`, `securityDeposit`. No salesperson block (uses `signoffNoSales()`).
- **Coverage classification:** **Covered (legacy)** — same template family as 3.1; legacy did not have a separate "balance received" template (it conflated with `BOOKING_RECEIPT`). The redesign separates these and that is the right call.
- **Notes:**
  - Uses **green accent** (`#2d6a4f`) header to signal "money done" — implicit branding logic not yet captured in `EmailTemplate` (`product-design/01-domain-model.md:378-379`). The template engine should support per-template accent colour.
  - References the SD invoice cadence again ("approximately 14 days before your arrival") — same comment as 3.1.

### 3.5 Balance Reminder (7 Days)

- **Mockup label:** "Balance Reminder (7 Days)"
- **Mockup trigger (verbatim):** *"Sent to client 7 days before balance due date"*
- **Specced triggering event(s):**
  - **`workflows/12-automation/scheduler-jobs.md` `AUTOMATION.SCHEDULER.PAYMENT_REMINDERS`** (`:7`), Stage 2 (`:26-40`): `isEmailSentBeforeCD = UtcNow.Date == checkoutDate.AddDays(-7).Date` for `"Rental Balance Payment"` → `BALANCE_PAYMENT` template (`workflows/11-integrations/email-delivery.md:110`).
  - **`product-design/03-workflows.md` flow 7 step 2** (`:359`) — *"Auto-reminder schedule. Configured per site (e.g., 60 days before, 45, 30, 14, 7, 3, 1, day-of, overdue +3, overdue +7)"*. The 7-day mark is one of those, and one of only two cadences (legacy) that ever fired.
- **Merge fields implied:** `clientFirstName`, `property`, `location`, `ref`, `arrive`/`depart`, `totalAmount`, `deposit`, `depositDate`, `balance`, `balanceDue`, `flywireUrl`, `payUrl`.
- **Coverage classification:** **Covered (legacy)** — direct legacy match.
- **Notes:**
  - Mockup uses `signoffNoSales()` — i.e., **no salesperson contact in the reminder**. Defensible (automated nudge) but conflicts with the legacy template style which usually carried the agent's name. `product-design/03-workflows.md:373` says **"each reminder is a queued email job"** — neutral on signature.

### 3.6 Balance Reminder (3 Days)

- **Mockup label:** "Balance Reminder (3 Days)"
- **Mockup trigger (verbatim):** *"Sent to client 3 days before balance due date"*
- **Specced triggering event(s):**
  - **`product-design/03-workflows.md` flow 7 step 2** (`:359`) — the 3-day mark is in the new cadence list. The **legacy scheduler does NOT have a 3-day trigger** — `workflows/12-automation/scheduler-jobs.md:31` only checks `AddDays(-7)`.
- **Merge fields implied:** Same as 3.5, plus `salespersonPhone` (used in the alertBox).
- **Coverage classification:** **Covered (product-design)** — explicitly new per flow 7.
- **Notes:**
  - Subject begins with **"REMINDER:"** (verbatim, all-caps) to nudge inbox visibility — a presentation choice the spec should formalise.
  - Body opens with a hard bold: *"Your balance payment is due in 3 days."*
  - This template requires the redesign to add the 3-day tier to the scheduler — see §4.

### 3.7 Balance Due Today

- **Mockup label:** "Balance Due Today"
- **Mockup trigger (verbatim):** *"Sent to client on the balance due date if payment not yet received"*
- **Specced triggering event(s):**
  - **`workflows/12-automation/scheduler-jobs.md`** Stage 2 (`:29`) — `isCheckoutDate = UtcNow.Date == checkoutDate.Date` for `"Rental Balance Payment"` → `BALANCE_PAYMENT`. Legacy reuses the same template for "7 days before" and "due today", which conflates urgency.
  - **`product-design/03-workflows.md` flow 7** "day-of" cadence (`:359`).
- **Merge fields implied:** Same as 3.5 / 3.6 — explicit ⚠ emoji in subject.
- **Coverage classification:** **Covered (legacy)** with the redesign improvement of using a **distinct template key** (red `#9b2335` accent vs. orange) rather than reusing `BALANCE_PAYMENT`.
- **Notes:**
  - Uses **danger-red header** (`#9b2335`) and a `danger` alert box. The body explicitly anticipates delivery delays (*"payments may take up to one working day to be reflected"*) — a useful disclaimer that the legacy template lacked.
  - The legacy scheduler doesn't differentiate cadence by template; this mockup forces the redesign into **three separate `EmailTemplate.key` rows**: `balance_reminder_7d`, `balance_reminder_3d`, `balance_due_today`.

### 3.8 Concierge Payment Request

- **Mockup label:** "Concierge Payment Request"
- **Mockup trigger (verbatim):** *"Sent to client when a concierge service quote has been approved and payment is required"*
- **Specced triggering event(s):**
  - **`workflows/09-booking/concierge.md` `BOOKING.CONCIERGE.REQUEST_PAYMENT`** (`:41-67`). Legacy template: `CONCIERGE_PAYMENT_TEMPLATE` (`workflows/11-integrations/email-delivery.md:122`).
  - **`product-design/03-workflows.md` flow 9 step 4** (`:442`) — *"Per line: 'Send payment link'"*.
- **Merge fields implied:** `clientFirstName`, `serviceItem`, `serviceInvoiceRef`, `serviceAmount`, `ref`, `property`, `location`, `arrive`/`depart`, `flywireUrl`, `payUrl`, salesperson block.
- **Coverage classification:** **Covered (legacy + product-design)**.
- **Notes:**
  - Mockup shows **a single service line per email** (`serviceItem`). The product-design flow 9 explicitly supports **batch-charge across multiple concierge lines into one payment link** (`product-design/03-workflows.md:442` `:455`). The mockup does not show that variant; need either a list-variant template or a repeatable section.
  - Uses `serviceInvoiceRef` (e.g., `VCX-002`). The redesign's `Payment` model in `product-design/01-domain-model.md:345` carries `external_reference`; a separate human-readable invoice ref is implied but not specced.

### 3.9 New Message from VC

- **Mockup label:** "New Message from VC"
- **Mockup trigger (verbatim):** *"Sent to client when their salesperson sends a message"*
- **Specced triggering event(s):**
  - **No specced workflow.** Closest: `product-design/03-workflows.md` flow 5 step 6 ("Email guest about this change") — but that's a structured change-notification, not a free-text message.
  - No `BookingMessage` / `Conversation` entity exists in `product-design/01-domain-model.md`. `EmailLog` (`:381-383`) captures sent emails but is forensic, not a messaging primitive.
- **Merge fields implied:** `clientFirstName`, `salesperson`, `property`, `ref`, `messagePreview`, salesperson block.
- **Coverage classification:** **New / speculative**.
- **Notes:**
  - Body says: *"Simply reply to this email and your response will be passed to {salesperson} directly. All correspondence is saved with your booking."* — this implies an **inbound-email-to-thread routing system** (e.g., per-booking reply-to addresses, à la `bookings+VC3345@reply.villacollective.com`). No such system is specced.
  - Cross-ref: this template most likely supports the future "guest-side correspondence panel" that `product-design/05-improvements-over-original.md:91` (booking detail tabs) implies but does not name. Pair with a sibling **client-portal messaging UI** spec.

### 3.10 Service Request Update

- **Mockup label:** "Service Request Update"
- **Mockup trigger (verbatim):** *"Sent to client when the status of a concierge service request changes"*
- **Specced triggering event(s):**
  - **No specced workflow.** Closest: `product-design/03-workflows.md` flow 9 step 3 (`:440`) — *"Each line has its own state machine identical to deposit's: `Awaiting` → `Sent` → `Paid` / `Failed`. Or `Included`."* — but flow 9 does not fire a guest-facing status email on transition.
  - Legacy: no template for this.
- **Merge fields implied:** `clientFirstName`, `serviceItem`, `serviceStatus`, `serviceDetail`, `ref`, `property`, `location`, `arrive`/`depart`, salesperson block.
- **Coverage classification:** **New / speculative**.
- **Notes:**
  - The mockup's demo values show a **post-supplier-confirmation update** (*"Chef Elena has been confirmed for your stay. She will arrive each evening at 18:30..."*). This implies the supplier link in `product-design/03-workflows.md:438` (concierge line item carries `supplier`) drives status transitions that the guest needs to know about.
  - Needs a new state — beyond `Paid` — for "service confirmed by supplier" / "service dispatched". This is a **richer state machine than flow 9 currently has**. Reconcile with `product-design/01-domain-model.md`'s `ConciergeLineItem` (not currently in the doc; would need to be added).

### 3.11 Pre-Arrival Information

- **Mockup label:** "Pre-Arrival Information"
- **Mockup trigger (verbatim):** *"Sent to client approximately 7 days before check-in"*
- **Specced triggering event(s):**
  - **No specced trigger.** `workflows/12-automation/scheduler-jobs.md` only checks `checkoutDate`-relative offsets and `arrivalDate == today`, not `arrivalDate - 7 days`.
  - **`workflows/10-payment/payment-collection.md:94`** mentions *"Our experience team will be in touch shortly with your pre-arrival information"* in the **Balance Payment Received** copy — i.e., the body of template 3.4 promises this template will be sent.
- **Merge fields implied:** `clientFirstName`, `property`, `location`, `arrive`/`checkIn`, `depart`/`checkOut`, `adults`/`children`, salesperson block. Generic text about "villa representative", "directions sent separately", "concierge".
- **Coverage classification:** **New / speculative**.
- **Notes:**
  - Body explicitly says **"Directions and a property location map will be sent to you separately"** and **"The property manager's contact details will be shared with you 48 hours before check-in"** — both of these are *additional emails that are not specced and not in this catalogue* (directions email, manager-contact email). The redesign needs to decide if those exist as separate templates or fold in.
  - Needs a new scheduler tier: `BookingScheduledMessage.kind=pre_arrival_7d`, fired by Celery beat against `Booking.arrive_date - 7d`.

### 3.12 Check-In Reminder (48h)

- **Mockup label:** "Check-In Reminder (48h)"
- **Mockup trigger (verbatim):** *"Sent to client 48 hours before their scheduled check-in time"*
- **Specced triggering event(s):**
  - **No specced trigger.** Adjacent: the SD reminder fires at `arrivalDate.Date == today` (`workflows/12-automation/scheduler-jobs.md:30 + :38`) but that's day-of, not 48 h ahead.
- **Merge fields implied:** `clientFirstName`, `property`, `location`, `arrive`/`checkIn`, `depart`/`checkOut`, salesperson block.
- **Coverage classification:** **New / speculative**.
- **Notes:**
  - Subject begins **"You arrive in 48 hours — ..."** — friendly tone, no urgency code.
  - The "Quick Checklist" section uses hardcoded ☑ glyphs and references **"Arrival directions have been sent separately"** — same dependency as 3.11 on a "directions" email that isn't in the catalogue.

### 3.13 Post-Stay Thank You

- **Mockup label:** "Post-Stay Thank You"
- **Mockup trigger (verbatim):** *"Sent to client 24–48 hours after check-out"*
- **Specced triggering event(s):**
  - **No specced trigger.** `product-design/03-workflows.md` mentions a `Completed` state (booking transitions through it post-stay) but no email is fired off it.
  - Legacy: no template.
- **Merge fields implied:** `clientFirstName`, `property`, `location`, `ref`, `arrive`/`depart`, salesperson block.
- **Coverage classification:** **New / speculative**.
- **Notes:**
  - Body asks for **feedback by reply** — i.e., no review-link, no NPS survey, no third-party (Trustpilot / Google) deep-link. The redesign could add a structured review-collection workflow but currently doesn't.
  - This template should ideally fire from a `Booking.status` transition `Confirmed → Completed` (which `product-design/03-workflows.md` references in passing — e.g., `:241` shows `Completed` in the editability table — without saying *when* the transition happens). The trigger probably wants to be `checked_out + 24h` to allow for late-departure tolerance.

---

## 4. Missing emails the workflows imply

These templates are demanded by the workflow specs but **absent from the mockup**. Each entry below cites the spec line that requires the email.

### Enquiry-stage

- **Enquiry auto-reply to guest** — `workflows/07-enquiry/enquiry-intake.md:33` (`VC_ENQUIRE_AUTO_REPLY`). Also called for as the post-submit acknowledgement in `product-design/03-workflows.md:60` (flow 1 — "Acknowledgement email queued (templated, site-branded, includes operator's signature)").
- **Internal enquiry notification to ops** — `workflows/07-enquiry/enquiry-intake.md:32` (`VC_ENQUIRE_EMAIL`). The "Slack notification" alternative in `product-design/03-workflows.md:62` does not replace the email.

### Quotation-stage

- **Quotation send** — `workflows/08-quotation/transmission.md:7-37` (`QUOTATION.TRANSMISSION.SEND_EMAIL`). The legacy subject is hardcoded **`"Quotation from Villa Collective"`** (`:26`). `product-design/03-workflows.md:102-104` describes the preview-then-send pattern.
- **Quotation viewed / read-receipt notification to ops (optional)** — implied by `product-design/01-domain-model.md:189` (`Quotation.status` includes `viewed`).

### Booking-stage

- **Owner approval — decline notification to guest** — `product-design/03-workflows.md:710` (flow 15 decline path): *"Guest email with apology + offer to rebook elsewhere"*. The owner-side decline endpoint exists; the guest-facing email does not.
- **Booking modification — change notice to guest** — `product-design/03-workflows.md:264` (flow 5 step 6): *"Checkbox 'Email guest about this change' (default on for confirmed bookings...). Preview email before send."* No mockup template.
- **Booking modification — change notice to owner** — `product-design/03-workflows.md:262, :277` (flow 5). Also `workflows/09-booking/booking-modification.md:32` mentions owner-confirmation template on Start/Update Booking.
- **Cancellation confirmation to guest (with itemised refund)** — `product-design/03-workflows.md:770` (flow 16): *"Guest cancellation email (preview-confirmed) with itemized refund"*.
- **Refund confirmation to guest** — `product-design/03-workflows.md:823` (flow 17): *"Refund confirmation email to guest (preview-confirmed for non-emergency; auto-fired for cancellation chains with template)"*.

### Payment-stage

- **Security deposit request (BT-refundable path)** — `workflows/11-integrations/email-delivery.md:111` (`SECURITY_DEPOSIT_PAYMENT`); `workflows/12-automation/scheduler-jobs.md:38` (fires on `isStayDate OR balance-7d`). The mockup references the SD invoice in the *body* of 3.1 / 3.2 / 3.4 but does not include the SD invoice email itself.
- **Initial / deposit "due today" reminder** — `workflows/12-automation/scheduler-jobs.md:34` (`INITIAL_PAYMENT_TEMPLATE`). The mockup has *only* balance reminders, not deposit reminders. If the deposit is requested via the "Proceed to Booking" template (3.0), is there still a chase email if the guest doesn't pay? The spec implies yes.
- **Stored-card refresh request** — `workflows/12-automation/scheduler-jobs.md:36` (`CC_CARD_UPDATE`) — fires when a CC-funded balance is due. No mockup template.
- **Overdue escalation to ops** — `product-design/03-workflows.md:365-366` (flow 7 step 5): *"When state becomes `Overdue`, a red banner appears on the booking, a row appears on operator dashboard, and an escalation email fires to a configured ops address."* No mockup template.

### Owner-stage

- **Owner — new booking notification** — Legacy: `OWNER_BOOKING_CONFIRM` (`workflows/11-integrations/email-delivery.md:114`). `product-design/03-workflows.md:182, :311` reference *"Owner notification (if owner has `notify_on_new_booking` flag)"*. Distinct from the Approval Request (3.3) — fires when no approval is needed.
- **Owner — booking change notification** — `product-design/03-workflows.md:262` (flow 5 — debounced).
- **Owner — booking cancellation notification** — `product-design/03-workflows.md:783` (flow 16).
- **Owner — availability change digest** — `product-design/03-workflows.md:508` (flow 10 — debounced).
- **Owner — rate change digest** — `product-design/03-workflows.md:647` (flow 13).
- **Owner — monthly statement** — `product-design/03-workflows.md:673` (flow 14 statements tab); `:862` (reports email-with-attachment).
- **Owner — damages claim notification** — `product-design/03-workflows.md:415` (flow 8 — "Owner notification if damages > threshold").
- **Owner — welcome email** — `product-design/03-workflows.md:596` (flow 12 onboarding side-effect).

### Internal / system

- **Hold-expiry notification to creating agent** — `workflows/12-automation/scheduler-jobs.md:91` (open question: *"Hold expiry should also notify the agent who created the hold"*). Implied by `product-design/03-workflows.md:493`.
- **Damages claim email to guest** — `product-design/03-workflows.md:414, :405` (flow 8 — *"Damages-claim email to guest"* with partial-refund itemisation).
- **Scheduled-report delivery** — `product-design/03-workflows.md:852` (flow 18: *"Email to recipients (multi-email picker, optional message)"*).
- **Concierge upsell to ops** — Legacy `UPGRADE_CONCIERGE_SERVICE_REQUEST` (`workflows/10-payment/checkout-flow.md:30`; `workflows/11-integrations/email-delivery.md:116`).
- **Magic-link / passwordless owner login** — `product-design/01-domain-model.md:313` (`MagicLink`), `:387` (`CodeAuthLog kind=magic_link`); `product-design/05-improvements-over-original.md:106`. Legacy `VC_USER_PASSWORD_RESET` (`workflows/11-integrations/email-delivery.md:120`).
- **2FA code dispatch** — `product-design/01-domain-model.md:387` (`CodeAuthLog kind=2fa_code`); legacy `EMAIL_AUTH_CODE_TEMPLATE`.

---

## 5. New email types (no triggering workflow)

These three (plus the two Communications templates) are **net new** — present in the mockup with no specced trigger or no domain entity backing them.

- **Pre-Arrival Information (`arrive - 7d`)** — needs a new scheduler tier alongside payments/holds in `workflows/12-automation/scheduler-jobs.md:84-93` (open questions). Suggested Celery beat task: `bookings.tasks.send_pre_arrival_messages`. The fire condition is `Booking.arrive_date - 7d AND Booking.balance_state == 'paid' AND Booking.status in {Confirmed, DepositPaid}`.
- **Check-In Reminder 48 h (`arrive - 48h`)** — same shape, second tier. Could be a single `BookingScheduledMessage` table with `(booking_id, kind, fire_at, sent_at)` rather than scattered Celery tasks. Aligns with the scheduler open question in `workflows/12-automation/scheduler-jobs.md:93` (*"a more robust pattern computes the trigger time at booking-time and stores `reminder_due_at` on a separate table"*).
- **Post-Stay Thank You (`checked_out + ~24h`)** — needs a `Booking.checked_out_at` timestamp (currently `Booking.status` transitions are observable but no `checked_out_at` is documented in `product-design/01-domain-model.md`).
- **New Message from VC** — implies a guest-portal messaging primitive. Sibling doc `02-client-portal.md` (in this same `mock_up_analysis/` directory, currently un-authored) should formalise. Needs: a `BookingMessage` entity (sender, recipient, body, created_at, booking FK), an inbound-email gateway (e.g., per-booking reply-to address), and an `EmailLog ↔ BookingMessage` link.
- **Service Request Update** — implies that the **concierge line-item state machine in `product-design/03-workflows.md:440`** needs to expand beyond payment states (`Awaiting / Sent / Paid / Failed / Included`) to include supplier-confirmation states (`Requested / SupplierConfirmed / Dispatched / Completed / Cancelled`). Each transition would emit a guest notification when the supplier-confirmation flag flips.

---

## 6. Implied template engine / admin tooling

The mockup demands more than `product-design/04-rest-api-surface.md:665-677` currently exposes. v1 ships read-only seeded templates; the mockup pre-figures v1.1 work.

- **Versioned templates with per-template accent / colour.** The mockup uses **five distinct accent colours** based on template intent — tan `#e6b380` (default/info), gold `#c0873a` (3-day urgency), red `#9b2335` (today/danger), green `#2d6a4f` (paid). `EmailTemplate` in `product-design/01-domain-model.md:378-379` carries only `subject_template`, `body_template`, `is_active`, `version` — needs an `accent_color` (or a richer `style_token` JSON) field.
- **Merge-field catalogue.** With ~30 distinct merge fields across 14 templates, an operator-facing reference is needed. The catalogue should ship as code per `product-design/04-rest-api-surface.md:667` (*"Templates ship as code/seed data in v1"*).
- **Locale / currency.** The mockup uses `€` throughout (Greek villa). Mocks do not show locale variants. `product-design/01-domain-model.md:35` codifies `Decimal + currency_code` storage; the template engine needs to format these per recipient locale. No mockup template displays currency-conversion-for-payer (Flywire conversion already done client-side per `workflows/10-payment/payment-collection.md:35`).
- **Preview-before-send** — already specced as a first-class component in `product-design/03-workflows.md:15` and `:959` (closing notes — reused across many flows) and called out as `product-design/05-improvements-over-original.md:55-59` (improvement #9: *"Every outbound email step surfaces a preview modal..."*). v1.1 endpoint deferred: `POST /email-templates/{id}:preview` (`product-design/04-rest-api-surface.md:677`).
- **Test-send.** Deferred to v1.1 per `product-design/04-rest-api-surface.md:677`.
- **Suppression list / bounce handling** — `product-design/01-domain-model.md:381` notes `EmailLog.status` includes `bounced`; the redesign should add a `SuppressedAddress` table for hard-bounces and complaints.
- **Resend / bulk-resend.** Deferred to v1.1 (`product-design/04-rest-api-surface.md:677`). `/bookings/{id}:resend-confirmation` is in MVP (`:471`).
- **From-address strategy** — All mockup footers signal **"@villacollective.com"** centrally rather than per-agent. The legacy `INTEGRATIONS.EMAIL.SEND_AS_USER` path (`workflows/11-integrations/email-delivery.md:46-66`) sends quote emails *from the agent's own SMTP*. The mockup does not show this variant. The redesign should decide whether to preserve per-agent send for quotes only (and standardise on the central from-address for everything in this catalogue).
- **Footer / branding lockup.** All mockup templates share the dark-grey footer with VC address, contact link, confidentiality notice (mockup `index.html:139-157`). This is a reusable component, not per-template content.

---

## 7. Implied data model & API additions

Reconciling the mockup with `product-design/01-domain-model.md` and `product-design/04-rest-api-surface.md`:

### Already present, reusable as-is

- **`EmailTemplate`** (`product-design/01-domain-model.md:378-379`) — fits for templates 3.0–3.8, 3.10, 3.11–3.13.
- **`EmailLog`** (`:381-383`) — captures every send with rendered body, status (queued/sent/delivered/opened/bounced/failed). Already references `booking` / `enquiry` / `quotation` as optional FKs.
- **`MagicLink`** (`:313`) — covers the `approveUrl` / `declineUrl` tokens in template 3.3.
- **`Notification` + `NotificationPreference`** (`:422-426`) — already supports per-user, per-kind, per-channel; sufficient for in-app variants of these emails.

### Net new

- **`BookingScheduledMessage`** (or `ScheduledEmail`) — a per-booking row carrying `(booking, kind, fire_at, sent_at, email_log)`. Replaces the legacy scheduler's "compute today's date and compare" pattern (`workflows/12-automation/scheduler-jobs.md:26-40`) with a precomputed row at booking creation. Needed for: balance reminders (7d/3d/0d), pre-arrival (7d), check-in (48h), post-stay (24h), SD invoice (14d before arrival).
- **`BookingMessage`** (or `Conversation` / `Thread` / `Message` triplet) — guest ↔ salesperson messaging primitive for template 3.9. Inbound email gateway needed (per-booking reply-to address).
- **`ConciergeLineItem.supplier_state`** — extra state axis on the existing line-item state machine for template 3.10. Currently `product-design/03-workflows.md:440` only models payment state.
- **`EmailTemplate.accent_color`** (or `style_token`) — for the five-colour palette per §6.
- **`Booking.checked_out_at`** — needed to fire template 3.13. `product-design/01-domain-model.md` Booking section does not currently document this timestamp.
- **`EmailEvent` (open / click / bounce)** — `EmailLog.status` carries the latest state, but per-event rows are needed for analytics (open-rate by template) and for the "polled" status chip in `product-design/03-workflows.md:49`. Provider webhook (SendGrid / Postmark / SES) needs an ingestion endpoint analogous to the Flywire webhook in `workflows/10-payment/payment-collection.md:48-99`.

### API additions implied

Building on `product-design/04-rest-api-surface.md`:

- `POST /bookings/{id}/messages` — send a free-text message to the guest (template 3.9), returns the rendered preview before send.
- `GET /bookings/{id}/messages` — thread history.
- `POST /bookings/{id}/concierge/{line_id}:notify-supplier-state` — trigger template 3.10.
- `POST /email-templates/{id}:preview` — v1.1 (already deferred per `:677`).
- `POST /email-templates/{id}:test-send` — v1.1.
- `POST /email-logs/{id}:resend` — v1.1.
- `POST /webhooks/email/{provider}` — open/click/bounce ingestion.

### `PropertyDescription` sections

Templates 3.1 / 3.2 / 3.3 use three text blocks: `villaInfo`, `furtherInfo`, `serviceInclusions`. `product-design/01-domain-model.md:62` lists the section enum as `overview / house_rules / villa_info / further_info`. **`service_inclusions` is missing from the section enum** — add it, OR drive `serviceInclusions` off `PropertyFeature` rows where `Feature.service_type = INCLUDED_SERVICE` (`product-design/01-domain-model.md:87`).

---

## 8. Open questions for product

1. **Are the omitted templates accidental or out-of-scope for this catalogue?** Specifically: enquiry auto-reply, quotation send, owner new-booking, owner-decline-to-guest, cancellation/refund, modification notice, SD invoice, deposit-due, overdue escalation, stored-card refresh, hold-expiry, damages, statement delivery, magic-link, 2FA. Some of these are obviously client-facing (cancellation, refund, modification, SD invoice) and *should* be in the same catalogue.
2. **Owner-facing email — same catalogue or separate?** Only one owner-facing template appears (Owner Approval Request). The legacy `OWNER_BOOKING_CONFIRM` + the redesign's many "owner notification" side-effects (`product-design/03-workflows.md:182, :262, :311, :415, :508, :596, :647, :670, :783`) suggest at least 7–10 owner-side templates. Are they planned for a separate "Owner Emails" catalogue? If yes, sibling doc is needed; if no, fold into this one.
3. **Should the messaging-channel emails (3.9, 3.10) fold into a unified Notification system?** `Notification` + `NotificationPreference` (`product-design/01-domain-model.md:422-426`) already exist for in-app channels. The two Communications templates effectively are email-channel mirrors of in-app notifications. Decision: one entity with `channel ∈ {email, in_app, sms, push}`, or two parallel systems?
4. **`holdExpiresIn = "5 working days"`** in the Proceed-to-Booking template — is this a real policy, or mock prose? `product-design/03-workflows.md:106` says **48 h** for quote-stage auto-holds; `workflows/12-automation/scheduler-jobs.md:51-64` says **7 days** for the legacy `AvailableStatus=40` hold. Three numbers; pick one and codify in `SystemDefaults`.
5. **Subject-line collision: 3.1 vs 3.2** — *"Booking Confirmed — Villa Elysian · 16th May 2026 – 23rd May 2026"* is byte-identical between the two confirmation variants. Gmail will thread them. Differentiate.
6. **Separate "Directions" and "Property Manager Contact" emails** — templates 3.11 and 3.12 reference these as "sent separately". Add to catalogue or merge into Pre-Arrival.
7. **The `[#TOKEN#]` vs `{:Token:}` placeholder syntaxes** in the legacy templates (`workflows/11-integrations/email-delivery.md:126`) — the mockup uses runtime JS concatenation, not a substitution syntax. The Django redesign should pick Django template syntax (`{{ booking.reference }}`) and convert seed data accordingly.
8. **Per-agent SMTP send (legacy quote path) vs central send** — preserve the "appears to come from the agent" capability for quotes (`workflows/08-quotation/transmission.md:28`) but route everything else through the central transactional provider? Or unify on central with agent shown only in the body / reply-to?
9. **Inbound-email handling for template 3.9 ("reply to this email and your response will be passed to {salesperson} directly")** — requires a per-booking reply-to alias (`bookings+VC3345@reply.villacollective.com`) and an inbound email parser. Out of scope, in scope but deferred, or assumed?
10. **Review collection on Post-Stay (3.13)** — the mockup asks for feedback by reply. Should the redesign add a structured review-collection step (Trustpilot / Google / internal)?
11. **`Booking Confirmation (Paid in Full)` — single template or just a `paid_in_full` rendering branch on `booking_confirmation`?** With Django templates the branch is trivial; one `EmailTemplate.key` could carry both renderings via a conditional. Decision affects seed data shape.
12. **Locale support** — when does Villa Collective need non-English variants? Not surfaced in the mockup but `product-design/01-domain-model.md:299` says `Guest.language` is captured.

---

## 9. Cross-reference quick map

| Mockup template | Closest spec citation |
|---|---|
| Proceed to Booking | `product-design/03-workflows.md:163` (flow 3 post-submit), `:305` (flow 6 Path A) |
| Booking Confirmation | `workflows/10-payment/payment-collection.md:73` (`SentEmailToPayerAndLeadGuest`), `workflows/11-integrations/email-delivery.md:113` (`BOOKING_RECEIPT`) |
| Booking Confirmation (Paid in Full) | (no direct cite; variant of above) |
| Owner Approval Request | `workflows/09-booking/booking-confirmation.md:47`, `product-design/03-workflows.md:697` (flow 15) |
| Balance Payment Received | `workflows/10-payment/payment-collection.md:73-74`, `product-design/03-workflows.md:363` |
| Balance Reminder (7 Days) | `workflows/12-automation/scheduler-jobs.md:31`, `workflows/11-integrations/email-delivery.md:110` (`BALANCE_PAYMENT`) |
| Balance Reminder (3 Days) | `product-design/03-workflows.md:359` (cadence) — **no legacy trigger** |
| Balance Due Today | `workflows/12-automation/scheduler-jobs.md:29-35`, `product-design/03-workflows.md:359` |
| Concierge Payment Request | `workflows/09-booking/concierge.md:41-67`, `workflows/11-integrations/email-delivery.md:122` (`CONCIERGE_PAYMENT_TEMPLATE`) |
| New Message from VC | (no spec) |
| Service Request Update | (no spec; partial: `product-design/03-workflows.md:440`) |
| Pre-Arrival Information | (no spec; `workflows/10-payment/payment-collection.md:94` body promises it) |
| Check-In Reminder (48h) | (no spec) |
| Post-Stay Thank You | (no spec) |

---

## 10. Recommended next steps

1. **Catalogue the missing owner-facing templates** in a sibling `mock_up_analysis/05-owner-emails.md` (this doc names the gap; that doc fills it).
2. **Add a `ScheduledEmail` / `BookingScheduledMessage` model spec** to `product-design/01-domain-model.md` to back the 5 new cadence tiers (balance −3d, pre-arrival −7d, check-in −48h, post-stay +24h, SD-invoice −14d). Replaces the legacy "compute today's date and compare" pattern.
3. **Lift `BookingMessage` / `ConciergeLineItem.supplier_state`** into the domain model — both implied by Communications templates.
4. **Resolve the `holdExpiresIn` discrepancy** (5 working days vs 48 h vs 7 days) before any template ships.
5. **Settle the per-agent vs central SMTP split** — write the decision into `workflows/11-integrations/email-delivery.md` so the implementation has one source of truth.
6. **Differentiate subject lines for templates 3.1 and 3.2** to avoid Gmail threading.
7. **Add `service_inclusions` (or equivalent) to `PropertyDescription` section enum**, or wire the inclusions block to `PropertyFeature` rows with `service_type = INCLUDED_SERVICE`.
8. **Spec the inbound-email gateway** that template 3.9's "reply to this email" affordance requires — out-of-scope for v1 is acceptable, but commit one way.
