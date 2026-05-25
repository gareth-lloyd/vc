# Client Booking Process — Mockup Analysis

> Source: https://vc-booking-process.netlify.app/
> Reviewed against: `django_res_design/workflows/`, `django_res_design/product-design/`
> **Headline:** Core mechanics (3-tier payment schedule, Flywire, lead/payer split, T&Cs, security-deposit handling) are extensively specced — call it ~85% coverage of what the mockup shows. The mockup's contribution is to **formalise the guest-facing checkout as a Django/React surface** with five discrete steps, an in-funnel Flywire embed, and a portal hand-off at the end. **It deliberately skips the entire pre-funnel** (homepage / property search / property detail / enquiry submission / quote review / quote-acceptance click) — which is the part of the journey that `workflows/08-quotation/lifecycle.md:54-58` flags as `[STUB]` and that operator-side spec workflows assume happens via a staff action, not a guest action.

---

## 1. Summary

The mockup renders a five-step guest-facing checkout funnel — **Summary → Details → T&C → Payment → Confirm** — for a single, already-issued booking (ref `VC3345`, Villa Castellana, Tuscany; 16th–23rd May 2026; party of 10 adults + 2 children; £48,000 total). Every screen carries a step indicator (`1 of 5` … `5 of 5`), forward/back navigation, and an FAQ accordion specific to that step. Payment hands off to an embedded Flywire widget that supports both Card (Visa/Mastercard/Amex) and Bank Transfer tabs without leaving the host SPA, and the confirmation screen links the guest to `portal.villacollective.com/VC3345`.

**Coverage estimate against the existing design corpus:**

| Concern | Spec coverage | Mockup novelty |
|---|---|---|
| 3-tier payment schedule (deposit/balance/SD) | High (`workflows/09-booking/payment-schedule.md`, `product-design/01-domain-model.md:317-340`) | UI presentation only |
| Lead/Payer split | High (`workflows/09-booking/booking-creation.md:36-42`, `product-design/01-domain-model.md:200-207`) | Guest-facing toggle UI |
| Flywire integration | High (`workflows/11-integrations/flywire-gateway.md`) | In-funnel embed (vs redirect) |
| Security-deposit pre-auth / BT-refundable split | High (`product-design/01-domain-model.md:331-341`, `workflows/10-payment/payment-preauth.md`) | Mockup only shows BT-refundable variant |
| T&C content (20 sections, versioning, acceptance audit) | **Low** — `TermsVersion` exists (`product-design/01-domain-model.md:245-248`) but no acceptance-audit entity | New requirement: `TermsAcceptance` |
| Additional-guest manifest | **Low** — implied by `Booking.adults/children/infants` but no per-guest rows | New entity: `AdditionalGuest` |
| Guest privacy consent | **Low** — `Guest.marketing_consent` exists but no booking-time consent receipt | New entity: `GuestPrivacyConsent` (or `AuditLog` entries) |
| Guest-side portal handover | **Low** — sibling doc `02-client-portal.md` covers, but the link contract is new |
| **Pre-funnel (search/enquiry/quote-accept)** | **Not in mockup** | n/a — flagged as `[STUB]` in `workflows/08-quotation/lifecycle.md:54-58` |

**The "missing entry point" callout.** The mockup opens at Step 1 — "Summary" — of an already-issued booking. There is no homepage, no property list, no property-detail page, no enquiry form, no quote view, and no "Accept this quote" button. Whoever sent the guest here already has:

- A `Booking` row with reference `VC3345` and a populated payment schedule (`Booking.status` = `awaiting_deposit` per `product-design/01-domain-model.md:217`).
- A magic-link or signed URL the guest clicked from email.
- A `Quotation.status = converted` (per `product-design/01-domain-model.md:189`).

The funnel therefore presupposes the prior path that is currently *least* specified. `workflows/08-quotation/lifecycle.md:23-25` is explicit: *"Client-clickable acceptance URL implementation is not in committed code; flow is staff-driven. Decide whether the redesign exposes a true self-service accept flow."* The mockup answers that question implicitly — yes, there is a guest-facing surface — but skips the screen that gets the guest there.

---

## 2. Funnel scope: what IS and IS NOT in the mockup

### IS in the mockup (the entire funnel)

| Step | Purpose | Key elements |
|---|---|---|
| **1 — Summary** | Show the guest what's been booked on their behalf | Booking ref, villa, dates, party, inclusions, sales contact, "I have reviewed and agree" checkbox |
| **2 — Details** | Capture lead-guest identity, payer-different toggle, additional-guest manifest, privacy consent | Title/name/address/phone form, payer toggle, "+ Add a guest" affordance, privacy policy checkbox |
| **3 — T&C** | Present 20 numbered legal sections, capture acceptance | Long scrollable copy, single "I have read and agree" checkbox |
| **4 — Payment** | Show 3-tier schedule, route the deposit to Flywire | Schedule table (Total/Deposit/Balance/SD), "Pay by Card via Flywire" / "Pay by Bank Transfer via Flywire" CTAs, support phone, embedded Flywire widget with Card/BT tabs |
| **5 — Confirm** | Receipt + next-steps + portal handover | Confirmation message, receipt block (deposit received, balance due, SD invoice scheduled), "Open my Villa Collective portal →" CTA, bank-transfer instructions variant for BT path |

### IS NOT in the mockup (deliberate scope gap vs a realistic guest journey)

| Phase | Where the spec already covers it | Mockup status |
|---|---|---|
| Public homepage / brand entry | Out of scope of `django_res/` rebuild — lives on the WordPress storefront(s) registered as `integrations.SyncRecord(provider=WORDPRESS_SITE)` (`product-design/01-domain-model.md:31-33`) | Absent |
| Property search / listing / filter | WordPress side; results syndicated outbound | Absent |
| Property detail page | WordPress side | Absent |
| Enquiry form intake | `workflows/07-enquiry/enquiry-intake.md:1-57` (`ENQUIRY.INTAKE.WEBSITE`) | Absent |
| Quotation render / preview to guest | `workflows/08-quotation/transmission.md:1-37` (`QUOTATION.TRANSMISSION.SEND_EMAIL`) | Absent |
| Self-service quote acceptance | `workflows/08-quotation/lifecycle.md:23-25` — explicitly `[STUB]` | Absent — yet the funnel presupposes it |
| Operator/staff "Start Booking" trigger | `workflows/09-booking/booking-creation.md:7-9` — currently the only path that creates a `VillaBooking` | Absent — but the mockup's Step 1 begins *after* this has happened |

This is the single most important observation for product: **the mockup's entry point is a booking that has already been created.** Whether by staff click or by a self-service quote-accept screen — that decision is not in the mockup and not yet decided in the spec.

---

## 3. Step-by-step specification

For each step: visible UI elements, implied data, validation, spec references, and departures.

### 3.1 Step 1 — Summary

**Header chrome:** Villa Collective logo · Help link · Contact link · step indicator (`1 of 5`).

**Visible content:**
- Salutation: `"Dear Mr Wood,"` (renders `Booking.guest.title + last_name`).
- Lead paragraph confirming `Villa Castellana, Tuscany, Italy` is on hold; warning about strict check-in/check-out adherence.
- Summary card (presented as labelled rows):
  - **Booking reference**: `VC3345` — i.e. `Booking.reference` (per `product-design/01-domain-model.md:48` reference prefixes live in `SystemDefaults`; the legacy `VC` prefix is now operator-configurable rather than hardcoded as in `workflows/09-booking/booking-creation.md:85`).
  - **Villa**: `Villa Castellana, Tuscany, Italy` — `Property.display_name`, `Property.region.name`, `Property.country.name`.
  - **Rental period**: `16th May 2026 — 23rd May 2026` — `Booking.from_date`, `Booking.to_date`.
  - **Number of nights**: `7` — derived.
  - **Party leader**: `Mr Ben Wood` — `Booking.guest`.
  - **Party size**: `10 Adults · 2 Children` — `Booking.adults`, `Booking.children`.
  - **Maximum occupancy**: `12 (sleeps 12 in 6 bedrooms)` — `Property.max_occupancy` + `Property.bedrooms`.
  - **Check-in/check-out**: `Check in 16:30 · Check out 10:30` — `PropertySettings.check_in_time`, `PropertySettings.check_out_time` (`product-design/01-domain-model.md:68`).
  - **Service inclusions**: free-text list ("Daily housekeeping · welcome hamper on arrival · private chef for 3 evenings · airport transfers from Pisa") — implied source is `ConciergeLineItem` rows with `payment_timing=included` (`product-design/01-domain-model.md:225-230`), plus possibly `Season.inclusion` (per `product-design/01-domain-model.md:131`).
  - **Villa information**: free-text bullets ("No smoking indoors · Children welcome · Pets not permitted · Air conditioning throughout · Private pool heated May–October") — implied source is `PropertyDescription(section='house_rules')` and/or `PropertyDescription(section='villa_info')` (`product-design/01-domain-model.md:62`).
  - **Sales contact**: `Sarah Mitchell · sarah@villacollective.com` — `Booking.assigned_to` (`product-design/01-domain-model.md:203`).

**Form / action:**
- Single checkbox: `"I have reviewed and agree to the Booking Summary above."`
- Single CTA: `"Next Step →"`.

**FAQ accordion (six items):** check-in/check-out flexibility, off-hours arrival, concierge add-ons, flight arrangement, `+` notation on max occupancy, exceeding max occupancy ("No").

**Spec references:**
- Booking summary fields all exist on `Booking` and `Property` per `product-design/01-domain-model.md:200-208`.
- The "sales contact" requires `Booking.assigned_to` (FK to `User`) to be set — that field already exists and is differentiated from external `agent` per `product-design/01-domain-model.md:203` and reconciliation issue #26.
- Service inclusions / villa information are not currently structured for guest display — see §7 for implied data model additions.

**Validation implied:**
- Step transition is gated on the checkbox.
- No server-side mutation on next-click — purely client-side UI state.

**Departures:**
- The legacy system has no equivalent guest "summary review" screen. Operators send a booking-confirmation email and a Flywire link; the guest never reviews a structured summary first. This is new.
- The "agree to Booking Summary" checkbox is a soft acknowledgement, not a contractual one (T&Cs handle the legal part). It should still be audit-logged as an `AuditLog` row keyed `booking.summary.acknowledged`.

### 3.2 Step 2 — Details

**Header:** step indicator (`2 of 5`); intro text framing lead-guest role.

**Lead-guest form:**
- `Title` dropdown (Mr/Mrs/Ms/Miss/Dr/Prof)
- `First name` (text)
- `Last name` (text)
- `Email` (text)
- `Address` (text — single line; collapses what would normally be Line 1 / Line 2)
- `City` (text)
- `Postcode` (text)
- `Country` (dropdown: UK/US/France/Germany/Italy/Spain/Other)
- `Phone` (text with country-flag selector — implies libphonenumber)

**Payer toggle:**
- Checkbox: `"The Payer for this booking is different from the Lead Guest"`.
- When ticked, reveals identical form shape but labelled "Billing address" rather than "Address".

**Privacy consent:**
- Checkbox: `"I agree to Villa Collective's Privacy Policy and consent to my personal data — and that of any additional guests I have added — being processed for the purposes of fulfilling this booking."` (links to a Privacy Policy URL — placeholder `#` in mockup).

**Additional guests section:**
- Instructional copy: "Add the rest of your party so they can receive the information you choose…"
- Single button: `"+ Add a guest"`.
- The mockup does not show the expanded form for an additional guest; it's a "tap to reveal" affordance.

**Navigation:** `← Previous Step` / `Next Step →`.

**FAQ accordion (five items):** what is a Lead Guest, what is a Payer, address questions for Lead vs Payer, FX explanation (interesting: explains that **currency conversion is based on the phone country code**).

**Spec references:**
- Lead/payer-different is squarely covered by `Booking.guest` + `Booking.payer` (`product-design/01-domain-model.md:203`) and by flow 3 in `product-design/03-workflows.md:146` ("Payer is different from guest" toggle exposes payer fields).
- The legacy `CheckoutPersonalInfo` shape covers the field set almost identically: `bookingId`, `bookingRefNo`, `title`, `firstName`, `lastName`, `addressLine1`, `addressLine2`, `town`, `postCode`, `country`, `countryCode`, `email`, `mobileNo`, `otherMobileNo`, plus an `isAdditionalInfo` flag and a parallel `CheckoutAdditionalInfo` row for a second guest (`workflows/10-payment/checkout-flow.md:12-22`).
- The legacy structure only supported **one** additional guest (`CheckoutAdditionalInfo`, singular). The mockup's `"+ Add a guest"` button implies arbitrary N — see §7.
- FX-by-phone-country-code does **not** appear in any current spec. Currency comes from `Booking.currency` / `Property.currency` (`product-design/01-domain-model.md:35-36`); the gateway converts at payment time. The "FX based on phone country code" guidance in the FAQ is a UI fiction or a non-binding hint and should be reconciled.

**Validation implied:**
- Required: title, first, last, email, address, city, postcode, country, phone.
- Email format validation, phone-number formatting via libphonenumber.
- Privacy checkbox required.
- If payer toggle on, all payer fields required.

**Departures:**
- A *named manifest* of additional guests is new. Legacy only knows party-size counters (`Booking.adults / .children / .infants`) and a single "additional checkout info" row.
- The privacy consent is currently `Guest.marketing_consent` (a single boolean on `Guest`, per `product-design/01-domain-model.md:299`). What the mockup captures is **booking-time data-processing consent** for the whole party — a different concept, with auditability needs (see §4 and §7).

### 3.3 Step 3 — Terms and Conditions

**Header:** step indicator (`3 of 5`); intro "Please read these Terms and Conditions carefully…".

**Content:** Twenty numbered sections rendered as scrollable copy. Section headers (verbatim):

1. Booking — T&Cs + Booking Summary are binding; conditional offer expires if payment not received.
2. The Parties — what the agreement covers (accommodation + included services).
3. The Villa — regular inspections; notify of material changes.
4. Rental Period — strict check-in/check-out adherence absent prior written agreement.
5. Payment Schedule — deposit, balance, security pre-auth all taken separately via Flywire; late payment cancels without refund.
6. Security Deposit — pre-auth required 3 days before arrival; held 5 days post-departure; *"not a charge — it is a card hold"*.
7. Cancellation by Client — sliding scale: `>56 days = deposit only`; `29–56 days = 50%`; `15–28 days = 75%`; `≤14 days = 100%`.
8. Cancellation by Villa Collective — alternative search or full refund within 14 days.
9. Changes to Bookings — date/property changes treated as cancellation/rebooking.
10. Conduct and Responsibilities — Party Leader ensures respectful behaviour; liable for damage.
11. Number of Guests — cannot exceed max occupancy; unauthorized guests cause immediate termination.
12. Pets — only if explicitly permitted, in writing.
13. Events and Gatherings — prohibited without Villa Collective + owner written consent.
14. Villa Condition — leave in same condition; standard cleaning included; extra charges for poor condition.
15. Pool and Facilities — endeavours-best disclaimer on availability.
16. Complaints — report immediately or within 24 hours; post-departure complaints not addressable.
17. Liability — Villa Collective acts as agent; not liable beyond direct control.
18. Force Majeure — refunds for unjustified amounts within 30 days.
19. Data Protection — processing per Privacy Policy.
20. Applicable Law — English Law; courts of England and Wales.

**Form / action:**
- Single checkbox: `"I have read and agree to the Booking Terms and Conditions."`
- Buttons: `← Previous Step` / `Next Step →`.

**Spec references:**
- `TermsVersion` entity (`product-design/01-domain-model.md:245-248`) already exists with `version` slug, `body_markdown`, `published_at`, `is_current`. The mockup's content **becomes the body of the first published `TermsVersion`** (e.g. `version = "2026-05"`).
- `Quotation.terms_version` and `Booking.terms_version` snapshot the version active at creation (same lines).
- API surface for the versioned T&Cs exists: `GET/POST /terms-versions`, `GET /terms-versions/current`, `POST /terms-versions/{version}:publish` (per `product-design/04-rest-api-surface.md:806-810`).
- **Missing:** no entity captures **acceptance** by a specific guest at a specific point in time. The check on the box must persist as more than ephemeral UI state — see §4 below.
- Section 5 (Payment Schedule) directly references Flywire and the deposit/balance/SD pattern that `workflows/09-booking/payment-schedule.md:1-46` formalises.
- Section 6 (Security Deposit) — pre-auth language matches the redesign's `pre_auth_hold` SecurityDeposit kind (`product-design/01-domain-model.md:336`) and revives `PAYMENT.PREAUTH.SECURITY_DEPOSIT` (`workflows/10-payment/payment-preauth.md:1-39`) which is currently `[DISABLED]` in legacy code. **However**, the mockup's Payment step (§3.4) does *not* show a pre-auth — it shows a BT-refundable SD invoiced separately. So the T&Cs and the Payment step are slightly inconsistent on the SD mechanism. See §9.
- Section 7 (Cancellation by Client) is a concrete tier table that should populate one of the `CancellationPolicy` named templates (`product-design/01-domain-model.md:369-372`); the `Booking.cancellation_policy` is already specced as a snapshot to insulate from policy changes.

**Validation implied:**
- Step transition gated on the checkbox.
- The checkbox click must persist a `TermsAcceptance` row (new — see §7) referencing the active `TermsVersion.version`.

**Departures:**
- Versioned T&Cs in the legacy system live in `wwwroot/templates/` static files (no DB record). The mockup formalises them as first-class content.
- Acceptance has no legacy equivalent — there's no "I agree" checkbox in the legacy flow. Acceptance currently relies on the implicit "guest paid the deposit = guest accepted." Mockup makes the acceptance explicit, separate from payment.

### 3.4 Step 4 — Payment

**Header:** step indicator (`4 of 5`); insurance warning: *"Important: Prior to making payment, the Lead Guest is responsible for ensuring the party has adequate travel insurance for this booking."*

**Payment Schedule Table:**
- Total Rental Amount: **£48,000** — `Booking.rental_amount`.
- Deposit: **£14,400** — `DepositPaymentTrack.amount` (30% of 48k).
- Balance: **£33,600** (due by 16th March 2026) — `BalancePaymentTrack.amount`, `due_date`.
- Security Deposit: **£4,800** (invoiced separately by bank transfer ~14 days before arrival) — `SecurityDeposit.amount`, `kind=bt_refundable`.
- Total Due Now: **£14,400** — derived (deposit amount).

**Security Deposit information panel:**
- Invoice receipt ~14 days before arrival.
- Payment method: bank transfer only.
- Refund: full within 14 days post-checkout (subject to inspection).

This is a **BT-refundable** flow per `SecurityDeposit.kind` (`product-design/01-domain-model.md:335-340`), not a pre-auth hold — even though the T&Cs section 6 describes pre-auth. See §9 conflicts.

**Payment-method selection (two big cards):**
- **Card Payment** — *"Visa, Mastercard or American Express via Flywire. Funds clear immediately…"* → button `"Pay by Card via Flywire →"`.
- **Bank Transfer** — *"Receive bank details for your country and currency via Flywire. Allow 1–2 business days for funds to clear…"* → button `"Pay by Bank Transfer via Flywire →"`.

**Auto-payment notice:** *"separate Flywire link sent for balance; no auto-charge — every payment requires your action."* This is a deliberate departure from `PAYMENT.PREAUTH.RECURRING_CHARGE` (`workflows/10-payment/payment-preauth.md:42-83`) which is `[DISABLED]` — confirming the redesign keeps the reminder-link pattern rather than reviving tokenized recurring charge.

**Support contact:** `+44 (0) 208 950 1588`.

**Navigation:** `← Previous Step` only — forward navigation is the act of paying.

**FAQ accordion (twelve items):** Flywire safety, deposit %, balance timing, stored cards, BT balance flow, splitting payments, balance-due-in-full edge case, what is a security deposit, SD invoicing, refundability, insurance.

**Flywire widget (embedded sub-screen / iframe-equivalent):**
- Heading: *"Scheduled payments"* with amount £14,400 charged today.
- Branded with "Powered by flywire".
- **Tab 1 — Debit/Credit Card:** currency GBP, supported cards VISA/MC/AMEX, single "Add your card" input, `PAY £14,400` button.
- **Tab 2 — Bank Transfer:** currency GBP, copy-block of bank details (Beneficiary `Flywire Payments — Villa Collective`, Bank `Barclays Bank plc, London`, sort code, account number, IBAN, SWIFT/BIC), demonstration amount and reference `FW-VC3345-DEP`, `I'VE SENT THE TRANSFER` button.

**Spec references:**
- 3-tier payment schedule generation is fully specced at `workflows/09-booking/payment-schedule.md:1-46` (`BOOKING.PAYMENT_SCHEDULE.GENERATE`) and `workflows/09-booking/booking-creation.md:46-58` step 2.
- `DepositPaymentTrack`, `BalancePaymentTrack`, `SecurityDeposit` 1:1-with-`Booking` model exists per `product-design/01-domain-model.md:321-340`.
- The "Total Due Now" framing matches `DepositPaymentTrack.amount` and the `Booking.outstanding_amount` denorm aggregate (`product-design/01-domain-model.md:208`).
- Flywire integration: `workflows/11-integrations/flywire-gateway.md:1-44` covers gateway config, endpoints in use, webhook cascade. The mockup's Card path corresponds to a new outbound charge (currently `[DISABLED]` per `workflows/10-payment/payment-preauth.md:42-83`); the BT path bypasses Flywire processing but uses Flywire's local-bank-details aggregator for currency.
- The mockup's "every payment requires your action" decision **answers** the open question in `workflows/10-payment/payment-preauth.md:82-83`: *"Decide for the redesign whether automated charging is desired (with explicit guest consent) or whether the reminder flow stays."* Mockup says: reminder flow stays.

**Validation implied:**
- "Pay by Card" handoff must produce a Flywire payment intent referencing `Booking.reference` (= `Booking.id` per `PAYMENT.COLLECTION.WEBHOOK_RECEIVE` `fields.invoice_id` shape, `workflows/10-payment/payment-collection.md:60`).
- BT path requires the operator/system to monitor inbound bank transfer and reconcile against `external_reference = FW-VC3345-DEP` (the Flywire reference, distinct from the human booking reference `VC3345`).
- On webhook `status=guaranteed`, `DepositPaymentTrack.status = paid` and downstream cascade fires (per `workflows/11-integrations/flywire-gateway.md:24-32`).

**Departures:**
- Legacy redirects the guest to a Flywire-hosted page (per `BookingUrl` stored on `VillaBooking`, `workflows/09-booking/booking-creation.md:62-65`). The mockup *embeds* the Flywire widget inside the SPA. This is technically allowable via Flywire's commercial widgets but is a deployment decision worth confirming — see §5.
- The "Total Due Now" amount in the mockup is just the deposit. If the booking is within `BalanceDueDays` of arrival, the spec's "Full-payment short-circuit" (`workflows/09-booking/payment-schedule.md:21-23`) means there *is* no deposit — single payment due today+2. The mockup does not show that variant.

### 3.5 Step 5 — Confirm

**Header:** step indicator (`5 of 5`); checkmark icon; confirmation message: *"Thank you, Ben — your stay is confirmed"*; summary line: *"Booking reference VC3345 · Villa Castellana · 16th — 23rd May 2026"*.

**Next-steps panel (three numbered items):**
1. **Confirmation email** — full booking confirmation with T&Cs and booking details as a PDF attachment, within minutes.
2. **Portal access** — *"Your Villa Collective portal is now live — manage concierge requests, payments, messages, and documents in one place."*
3. **Your concierge team** — *"Sarah Mitchell will be in touch shortly to introduce your dedicated concierge and discuss your stay arrangements."*

**Receipt block:**
- Deposit received: £14,400 — today.
- Method: Card ending •••• 4242 (via Flywire).
- Balance due: £33,600 — by 16th March 2026.
- Security deposit invoice: £4,800 by bank transfer — sent ~14 days before arrival.
- Receipt sent to: `ben@mojomedia.co.uk`.

**CTA:** `"Open my Villa Collective portal →"` linking to `https://portal.villacollective.com/VC3345`.

**Bank-transfer instructions variant** (shown if guest picked BT in Step 4):
- Salutation, instructions to complete payment within 48 hours.
- Account Name: Villa Collective; Bank: Barclays Bank PLC; Sort Code: 20-00-00; Account Number: 12345678; Reference: VC3345; Amount: £14,400.
- Processing note: 2–3 business days to clear.

**Spec references:**
- `BookingDocument` exists for generated PDF artefacts (`product-design/01-domain-model.md:243`) — the confirmation PDF maps to `BookingDocument(kind='confirmation')`.
- The receipt corresponds to a `PaymentEvent` row with `status=succeeded`, `payment_method=card`, plus `PaymentInstrument` with `last_four=4242`, `brand=visa` (or whatever) — per `product-design/01-domain-model.md:342-350`.
- `EmailLog` (`product-design/01-domain-model.md:381-384`) tracks the confirmation email delivery.
- Portal link semantics — see §6.

**Validation implied:**
- The screen renders only after the deposit `PaymentEvent` returns `status=succeeded` from Flywire (Card path) OR after the guest clicked "I've sent the transfer" (BT path — but at that point `DepositPaymentTrack.status` is `link_sent` / pending operator reconciliation, not `paid`).
- For the BT path, the confirmation message *"your stay is confirmed"* is technically premature — payment isn't actually received. The mockup glosses this. Spec needs a distinct "Awaiting payment confirmation" terminal screen for BT.

**Departures:**
- Legacy has no SPA "confirm" page — the guest sees Flywire's success page and then receives an email. Mockup adds an in-app receipt + portal handover, materially better.
- The portal link is unprotected — `https://portal.villacollective.com/VC3345` exposes a booking reference as the URL. The portal itself must require authentication (magic link / passwordless — `MagicLink` entity exists per `product-design/01-domain-model.md:312`) and **not** treat the reference as a secret.

---

## 4. T&C handling — a distinct gap

The mockup formalises three things that the existing spec only partially covers:

1. **The 20-section content**. This is now the canonical *body* of `TermsVersion(version='2026-05', is_current=True)`. The text needs lawyering, but it is the corpus the system must store and render.

2. **Versioning of the content**. `TermsVersion` exists (`product-design/01-domain-model.md:245-248`, `product-design/04-rest-api-surface.md:802-810`) with the right shape — append-only, `is_current` partial unique, no PATCH/DELETE. The mockup itself doesn't show admin tooling for this, but the public read endpoint `GET /terms-versions/current` (`product-design/04-rest-api-surface.md:808`) is what Step 3 must call to render the body.

3. **Acceptance by the guest at a specific point in time**. **This is not in the spec.** The data model needs:

   ```text
   TermsAcceptance
     - id (UUID)
     - booking (FK Booking)
     - guest (FK Guest)  # lead guest (the actor who ticked the box)
     - terms_version (FK TermsVersion, snapshot)
     - accepted_at (timestamp)
     - ip_address (string, audit)
     - user_agent (string, audit)
     - acceptance_kind (enum: 'summary_review' | 'terms_and_conditions' | 'privacy_consent')
   ```

   Alternatives:
   - Reuse `AuditLog` (`product-design/01-domain-model.md:419-420`) with `action='booking.terms.accepted'`, `entity_kind='Booking'`, `entity_id=booking.id`, `metadata={terms_version, kind, ip, ua}`. Lower lift; sufficient for audit but less queryable.
   - The `Quotation.terms_version` / `Booking.terms_version` snapshot fields (`product-design/01-domain-model.md:248`) record *which* version was active at creation; they do not record *that* the guest then accepted it. The two are different — a version is snapshotted as soon as the booking is created (server-side), but acceptance is the guest's later ticking-of-the-box.

   **Recommended:** a dedicated `TermsAcceptance` table. It's a regulatory artefact (think: dispute, GDPR Article 7 — "demonstrable consent"); having a queryable row beats a JSON blob inside `AuditLog`.

4. **Admin tooling to publish a new version**. `POST /terms-versions/{version}:publish` exists in the surface (`product-design/04-rest-api-surface.md:810`). The redesign needs an admin SPA screen — currently nowhere in `product-design/03-workflows.md` (the 20 workflows skip T&C admin). Add a flow.

5. **Effect of publishing a new version on in-flight bookings**. Per spec: existing bookings keep their snapshotted `terms_version`. Good. New bookings created after publish get the new version. **Question**: what about a booking that's been created but the guest hasn't yet hit Step 3? The snapshot was taken at booking creation, so the guest sees what was current then — even if a new version has since published. That's defensible (the guest sees the version they're agreeing to) but worth confirming.

---

## 5. Payment handoff — Flywire integration

The mockup makes one deployment decision and re-confirms several others:

**Decision: in-funnel Flywire widget, not a redirect.** Step 4's "Pay by Card via Flywire →" reveals a sub-screen (presumably an embedded Flywire widget / iframe) within the SPA rather than redirecting to a Flywire-hosted page. The widget surfaces both Card and BT tabs without leaving the host.

This is materially different from legacy. The legacy redirect-model is implicit in `workflows/09-booking/booking-creation.md:62-65`:

> Generate WordPress checkout URL: Build checkout payload with personal info, payment schedule, villa details. `_apiService.PushVillaBookingToWP(payload)` → POST to `{site}/Import_Booking`. Persist the returned URL: `UPDATE VillaBooking SET BookingUrl='{url}' WHERE Id={id}`.

— i.e. the legacy generates a Flywire URL up-front and the booking-confirmation email points the guest at it.

**The redesign should pick one and document it.** The mockup's embedded model has implications:
- Flywire offers both hosted-payment-page and embedded-checkout SDKs. The choice affects PCI-DSS scope. The Charge endpoint `/payments/v1/payments/charge` (`workflows/11-integrations/flywire-gateway.md:18-22`) is server-to-server and doesn't include a guest-facing UI; for an embedded UI you typically use Flywire's `RecipientCheckout` widget. Confirm with Flywire which SDK matches the mockup.
- `BookingUrl` stored on `VillaBooking` (legacy) is no longer necessary if the SPA generates the payment-intent on demand. Drop the field; on the Django side, the booking just holds the `DepositPaymentTrack` and the SPA hits a `POST /bookings/{id}/deposit:create-payment-intent` (or similar) to mint a Flywire checkout session at the moment Step 4 loads.
- The Step 4 sub-screen presumably wraps the Flywire widget in a chrome that preserves "← Previous Step" navigation. That's a Flywire-widget integration concern.

**Reconfirmations:**
- *Flywire is the gateway.* No multi-provider abstraction in v1 (`workflows/11-integrations/flywire-gateway.md:41-43`).
- *Webhook is the source of truth for `paid` status.* Per `workflows/10-payment/payment-collection.md:50-93`. The "Pay £14,400" button click is not what marks the deposit `paid` — the webhook callback is. The SPA polls or subscribes to determine when to advance to Step 5.
- *Signature verification and webhook idempotency must be wired.* Per `workflows/11-integrations/flywire-gateway.md:34-39` — these are explicit `[SECURITY]` gaps in legacy and must be fixed in the redesign.
- *No auto-charge for the balance.* The mockup re-confirms the reminder-link pattern from `workflows/10-payment/payment-preauth.md:80-83`.

**Pre-auth path absent from mockup payment step.** Even though T&C section 6 describes a pre-auth SD held on card, Step 4 routes the SD as BT-only ("invoiced separately ~14 days before arrival"). The pre-auth flow (`workflows/10-payment/payment-preauth.md:1-39`) is therefore not actually exercised in this mockup. See §9 for the conflict.

---

## 6. Portal handoff at confirmation

The final CTA — `"Open my Villa Collective portal →"` linking to `https://portal.villacollective.com/VC3345` — is the bridge to a separate, currently-undesigned product surface.

**What this implies:**

- A guest-facing client portal exists. Its design is the subject of sibling document `02-client-portal.md` (per the user's brief; the file is not in the corpus yet).
- The portal is hosted at a distinct subdomain (`portal.villacollective.com`) — separate from the public marketing site (`villacollective.com`, the WordPress storefront(s)) and presumably from the staff back-office.
- The URL pattern `/VC3345` is a booking-reference deep link. Authentication is *not* in the URL; the portal must independently authenticate via the existing `MagicLink` flow (`product-design/01-domain-model.md:312-313`) — i.e. clicking the link from the confirmation email or while still authenticated in the booking-funnel session.

**Open question:** is the booking funnel mockup hosted on the *portal* subdomain (so the session persists), or on the public site (so the link transition is a fresh-auth flow)? The mockup itself doesn't say. Most natural design: the funnel lives on `portal.villacollective.com` (since the guest is already authenticated by a magic link sent with the quotation acceptance), the confirmation CTA is just a navigation within the same authenticated session.

**Scope for the portal (per Step 5 next-steps copy):**
- Concierge requests
- Payments (balance, SD invoice)
- Messages
- Documents (T&Cs PDF, confirmation, invoices)

This aligns with `BookingDocument` (`product-design/01-domain-model.md:243`), `ConciergeLineItem` (`product-design/01-domain-model.md:225-230`), `EmailLog` (`product-design/01-domain-model.md:381-384`), `BalancePaymentTrack`, `SecurityDeposit`.

---

## 7. Implied data model additions

Beyond the entities already in `product-design/01-domain-model.md`, the mockup implies these new (or extended) tables:

### 7.1 `TermsAcceptance` (new)

Captures the guest's tick-of-the-box at Step 3. See §4 for full rationale.

```text
TermsAcceptance
  booking          FK Booking
  guest            FK Guest        # lead guest
  terms_version   FK TermsVersion  # snapshot
  acceptance_kind  enum: 'summary' | 'terms' | 'privacy'
  accepted_at      datetime
  ip_address       inet
  user_agent       text
```

Three rows per booking (one per checkbox). Append-only — no edits, no deletes.

### 7.2 `AdditionalGuest` (new)

The mockup's `"+ Add a guest"` Step-2 affordance implies a per-guest manifest beyond `Booking.adults` / `.children` counts.

```text
AdditionalGuest
  booking      FK Booking
  title        enum / text
  first_name   text
  last_name    text
  email        text, nullable
  phone        phonenumberfield, nullable
  age_band     enum: 'adult' | 'child' | 'infant'
  date_of_birth date, nullable
  dietary_notes text, nullable
  accessibility_notes text, nullable
  display_order int
```

Note: legacy supported exactly one additional guest via `CheckoutAdditionalInfo` (`workflows/10-payment/checkout-flow.md:21-22`). The redesign needs N. Cardinality: `Booking 1 ─── many AdditionalGuest`.

Open question: do additional guests double as `Guest` records (so they can have their own logins / GDPR scope)? The Step-2 instruction says "so they can receive the information you choose…" — implying yes, they have communication channels. If so, `AdditionalGuest` might fold into `Guest` with a `BookingGuest` join carrying the per-stay metadata (display order, role-in-party). Cleaner.

### 7.3 `GuestPrivacyConsent` (new — or use `AuditLog`)

The Step-2 privacy checkbox grants data-processing consent for the lead guest *and* all named additional guests. GDPR Article 7 makes consent demonstrable: who consented to what, when, on what version of the privacy policy.

Option A — dedicated row, parallel to `TermsAcceptance`:

```text
GuestPrivacyConsent
  booking            FK Booking
  granted_by_guest   FK Guest
  privacy_policy_version  text   # mirror of TermsVersion pattern, but for privacy policy
  scope              enum: 'lead_only' | 'lead_and_additional'
  granted_at         datetime
  ip_address         inet
  user_agent         text
```

Option B — collapse into `TermsAcceptance` with `acceptance_kind='privacy'`. Cleaner if the privacy policy is also versioned as a `TermsVersion`-shaped row (`policy_kind` discriminator: `terms` vs `privacy`).

### 7.4 Display-only structured content on `Property` / `Booking`

The Summary step exposes free-text bullets that the spec currently stores as rich-text per-section:

- "Service inclusions" — implied source is `Booking.concierge_lineitems.filter(payment_timing=included)` (`product-design/01-domain-model.md:225-230`). The bullets in the mockup are flat strings; if rendered from `ConciergeLineItem` rows, each `name` becomes a bullet.
- "Villa information" — implied source is `PropertyDescription(section='house_rules')` or `PropertyDescription(section='villa_info')` (`product-design/01-domain-model.md:62`). The mockup renders them as comma-separated bullets, which suggests a more structured representation (e.g. `PropertyFeature` rows with a `display_in_summary` flag, or a dedicated `PropertyHighlight` mini-entity).

No new entity strictly required, but the templating from existing entities to the Step-1 display strings should be specced in `02-frontend-design.md`-equivalent.

### 7.5 No change to `Booking`, `DepositPaymentTrack`, `BalancePaymentTrack`, `SecurityDeposit`

The payment model already supports everything Step 4 needs. The mockup's £14,400 / £33,600 / £4,800 split matches the legacy `BOOKING.PAYMENT_SCHEDULE.GENERATE` semantics 1:1 (`workflows/09-booking/payment-schedule.md:18-30`).

---

## 8. Implied API surface additions

Beyond endpoints already in `product-design/04-rest-api-surface.md`, the mockup implies:

| Step | Endpoint | Purpose |
|---|---|---|
| 1 | `GET /bookings/{ref}/checkout-summary` | Hydrate Step 1 — joined `Booking + Property + PropertySettings + concierge_inclusions + property_descriptions + assigned_to`. Or compose from existing `GET /bookings/{id}` (and let the SPA join). |
| 1 | `POST /bookings/{ref}/checkout-summary:acknowledge` | Persist the Step 1 checkbox tick as `AuditLog` row / `TermsAcceptance(kind='summary')`. |
| 2 | `GET /bookings/{ref}/details` | Return current lead-guest & payer & additional-guest state for prefilling. |
| 2 | `PUT /bookings/{ref}/details` | Save the Step 2 form: lead guest, payer-different flag + payer fields, additional guests, privacy consent. Persists `Guest`/`AdditionalGuest`/`GuestPrivacyConsent` rows. |
| 3 | `GET /terms-versions/current` | (Already in spec, `04-rest-api-surface.md:808`) — Step 3 reads this to render the body. |
| 3 | `POST /bookings/{ref}/terms:accept` | Persist `TermsAcceptance(kind='terms')`. |
| 4 | `POST /bookings/{ref}/deposit:create-payment-intent` | Server-to-Flywire to mint a checkout session; returns the iframe URL or widget params. |
| 4 | `POST /bookings/{ref}/deposit:mark-bt-intent` | Guest clicked "I've sent the transfer" — flips `DepositPaymentTrack.status` to `link_sent` / `pending_bt_reconciliation`. |
| 4 (existing webhook) | `POST /webhooks/flywire` | Already specced at `workflows/10-payment/payment-collection.md:48-99`; the redesign must verify signature and dedupe. |
| 5 | `GET /bookings/{ref}/confirmation` | Hydrate Step 5 — joined `Booking + last_succeeded_payment_event + balance_track + security_track + portal_url`. |

All endpoints should be `Booking.reference`-keyed at the URL (not `Booking.id`), since the URL is a deep link from a magic-link email and the reference is the human-shareable token. Authentication via magic-link session — the same surface used for the client portal.

---

## 9. Conflicts with existing specs

### 9.1 Operator-vs-guest entry point

`workflows/09-booking/booking-creation.md:7-9` defines the booking-creation trigger as the operator's `"Start/Update Booking"` or `"Start Booking - No Send"` button — i.e., **staff-driven**. The mockup begins at Step 1 of a booking that already exists — **guest-driven** consumption of a pre-issued booking.

**These are not in conflict per se** — the operator clicks "Start Booking", that creates the booking and emails the guest the funnel link. **But the spec needs to make this two-actor handoff explicit**: who creates the booking, when does the guest become aware of it, what URL do they click. Currently `workflows/09-booking/booking-creation.md` step 7 only says *"Send guest email — `SentEmailAsync(EmailTemplate.INITIAL_PAYMENT_TEMPLATE, QuotationNo)`"* — the email points to a `BookingUrl` (Flywire-hosted, single-purpose) rather than the new five-step funnel.

**Resolution:** add a new workflow file `workflows/09-booking/guest-checkout-funnel.md` that ties the operator-side "Start Booking" to the guest-side five-step funnel, specifies the email template that links them, and documents the magic-link auth that lets the guest land on Step 1.

### 9.2 Self-service quote acceptance is `[STUB]` — but the mockup presumes it works

`workflows/08-quotation/lifecycle.md:23-25`:

> "Client-clickable acceptance URL implementation is not in committed code; flow is staff-driven. Decide whether the redesign exposes a true self-service accept flow (with token + secure URL)."

The mockup picks "yes" — implicitly. The guest is already past quote-acceptance when they land on Step 1. Either (a) the operator manually converted the quote to a booking and the funnel begins from there, or (b) the guest clicked "Accept this quote" on a screen that isn't in this mockup, and that click *created* the booking before kicking off the funnel.

Path (b) is the more user-friendly model and is what the mockup implies. **The spec needs to add this missing screen** — a "Quote Review & Accept" flow that creates the booking. Suggested ID: `QUOTATION.LIFECYCLE.SELF_SERVICE_ACCEPT`. It would fold into `workflows/08-quotation/lifecycle.md` next to `CONVERT_TO_BOOKING`.

### 9.3 Security deposit: T&Cs say pre-auth; Payment step does BT-refundable

T&C section 6 (per the mockup): *"Pre-auth required 3 days before arrival; held 5 days post-departure; 'not a charge — it is a card hold'"* — describes the `SecurityDeposit.kind = pre_auth_hold` path (`product-design/01-domain-model.md:336`) which revives `PAYMENT.PREAUTH.SECURITY_DEPOSIT` (`workflows/10-payment/payment-preauth.md:1-39`).

Step 4's SD panel: *"Invoiced separately by bank transfer ~14 days before arrival… refund: full within 14 days post-checkout."* — describes `SecurityDeposit.kind = bt_refundable` (`product-design/01-domain-model.md:336`).

These are the two `SecurityDeposit.kind` values from the spec — but the mockup shows both in the same flow as if they're the same thing. They're not. The redesign must:

- Either pick one canonical kind per booking (driven by `PropertyFinance.security_deposit_kind` setting), and render only that one's copy & UI.
- Or render both kinds' content but make Step 4's panel switch based on the booking's actual configured kind.

The mockup's `SecurityDeposit.kind = bt_refundable` example data should not have surfaced the pre-auth T&C wording. Treat this as a copy-bug in the mockup; the underlying model is fine.

### 9.4 Mockup amount format vs spec money model

The mockup shows `£48,000` etc. as integers. The spec stores `Decimal(12, 2)` plus `currency_code` (`product-design/01-domain-model.md:35-36`). No real conflict — the SPA formats per locale — but ensure the rendered string has no rounding ambiguity for non-integer amounts.

### 9.5 The "Sales contact" Sarah Mitchell

Step 1 names a sales contact (`Sarah Mitchell · sarah@villacollective.com`). The spec's `Booking.assigned_to` is FK to `User` (`product-design/01-domain-model.md:203`) with `email` as alt-PK (`product-design/01-domain-model.md:304`). The contact's email is shown directly to the guest — that means the staff member's "external-facing" email and their internal user email might want to be distinct. Spec already accommodates: `User.email` is the login, and a `User` could have a `display_email` field. Add to the User entity if not already.

### 9.6 Mockup CTA "Pay by Card via Flywire" vs server-side intent creation

Mockup implies clicking "Pay by Card" *immediately* shows the Flywire widget. Reality: the SPA needs to call `POST /bookings/{ref}/deposit:create-payment-intent` to mint a Flywire session id, then load the widget with that id. That round-trip implies a short loading state — not shown in the mockup, but expected. No real conflict; flag for FE engineering.

### 9.7 "Total Due Now" assumes 3-tier; spec also handles 1-tier "full-payment short-circuit"

Per `workflows/09-booking/payment-schedule.md:21-23`:

> "If `daysToArrival < BalanceDueDays` → Full payment: skip deposit, single line due today+2."

The mockup does not show this variant. If the booking is within (default) 56 days of arrival when the funnel loads, Step 4 should show a single "Total Due Now: £48,000" line. The redesign needs both copy variants.

---

## 10. Open questions for product

These are the decisions the mockup *prompts* but does not *answer*. Surface to product for resolution before Django/React build:

1. **Where does the guest enter the funnel?**
   - Option A: Email link to a quote → guest accepts → booking is created → guest is redirected to Step 1.
   - Option B: Operator creates booking via "Start Booking", emails guest a magic link → guest lands on Step 1.
   - Option C: Both — quotes via A, direct bookings via B.
   - Mockup implies the booking pre-exists. Spec (`workflows/09-booking/booking-creation.md`) describes B. The user-facing pre-funnel for A is `[STUB]` (`workflows/08-quotation/lifecycle.md:54-58`).
   - **Recommendation:** Decide whether v1 needs A. If yes, add `QUOTATION.LIFECYCLE.SELF_SERVICE_ACCEPT` workflow.

2. **Who creates the booking — auto on quote acceptance, or staff-triggered?**
   - Currently staff-triggered. Self-serve acceptance would auto-create. The mockup doesn't say.
   - **Recommendation:** Self-serve quote acceptance auto-creates the booking with status `awaiting_deposit` and triggers the funnel email. This is materially better UX; the spec supports it (the booking-creation workflow can be invoked by the API on behalf of the guest given a quotation id + acceptance token).

3. **Where does the funnel live — Django/React SPA, or kept on WordPress?**
   - Legacy currently has the checkout on WordPress (`workflows/10-payment/checkout-flow.md:8` — `POST /api/WordPressApi/Payment/SaveCheckoutInfo`).
   - The mockup is clearly an SPA (step indicator, FAQ accordions, embedded Flywire widget).
   - **Recommendation:** Move to the Django/React SPA at `portal.villacollective.com`. The legacy `/api/WordPressApi/Payment/*` endpoints can stay as a temporary shim during migration but should be deprecated post-cutover. Confirm with the data-migration playbook (`django_res/data_migration/CUTOVER.md`).

4. **T&C versioning workflow:**
   - Who can publish a new `TermsVersion`? (Spec admin only.)
   - What's the cadence — annual? On legal change?
   - Is there an admin SPA screen to draft / preview / publish? **Not currently in any of the 20 workflows in `product-design/03-workflows.md`.** Add one.

5. **T&C acceptance audit trail granularity:**
   - Dedicated `TermsAcceptance` table or `AuditLog` row? (See §4 / §7.1.)
   - **Recommendation:** dedicated table. Regulatory artefact.

6. **Privacy policy versioning:**
   - Is the Privacy Policy versioned the same way as T&Cs? The mockup links to a Privacy Policy URL but doesn't show its content.
   - **Recommendation:** Yes — reuse `TermsVersion` shape with a `kind` discriminator (or add a `PrivacyPolicyVersion` mirror).

7. **Additional-guest manifest scope:**
   - Is the manifest required or optional? (Mockup makes it optional — "+ Add a guest".)
   - Are named additional guests `Guest` records (with their own GDPR scope) or denormalised `AdditionalGuest` rows on the booking?
   - **Recommendation:** Make them `Guest` rows via a `BookingGuest` join carrying the per-stay metadata (role-in-party, display order). Easier GDPR erasure flows.

8. **Security deposit kind: per-booking or per-property?**
   - `PropertyFinance.security_deposit_*` already exists (`product-design/01-domain-model.md:71`).
   - The mockup shows only BT-refundable. Spec supports both kinds.
   - **Recommendation:** Default per `PropertyFinance`, optionally overridable per booking by the operator. Step 4's SD panel renders the configured kind's copy.

9. **Flywire embedded vs hosted:**
   - Mockup implies embedded. Legacy used hosted.
   - **Recommendation:** Embedded if Flywire's `RecipientCheckout` widget supports the necessary UX (multi-currency BT, Card tabs in one). Otherwise stay hosted and bring the widget chrome inline as much as possible.

10. **Balance and SD due dates rendering:**
    - Mockup shows hardcoded "16th March 2026" and "~14 days before arrival". Both are derivable from `BalancePaymentTrack.due_date` and `SecurityDeposit.due_at`. Confirm formatting (`PropertySettings.timezone` for display).

11. **The portal CTA target — what does `https://portal.villacollective.com/VC3345` actually render?**
    - Sibling doc `02-client-portal.md` defines. Confirm the deep-link contract: `/VC3345` → render `Booking` detail dashboard, scoped to that booking. Auth via magic link.

12. **Auto-payment for the balance:**
    - Mockup reconfirms "no auto-charge — every payment requires your action." Spec's `PAYMENT.PREAUTH.RECURRING_CHARGE` is `[DISABLED]` (`workflows/10-payment/payment-preauth.md:42-83`). Confirm permanently dropping recurring-charge from v1.

13. **What happens on Card decline at Step 4?**
    - The Flywire widget surfaces an error; the SPA stays on Step 4 with the error inline.
    - Booking state stays `awaiting_deposit`. No state change.
    - `PaymentEvent` row with `status=failed`, `error_message=<reason>` is recorded (`product-design/01-domain-model.md:342-348`).
    - Guest retries — same Flywire intent? New intent? Confirm Flywire's retry semantics.

14. **What happens on Step 4 BT path before reconciliation?**
    - Guest clicks "I've sent the transfer" → SPA proceeds to Step 5 (per mockup).
    - But the deposit isn't actually `paid` — it's `link_sent` / `pending_bt_reconciliation` until the operator records receipt or the Flywire-side BT lands.
    - Step 5's *"your stay is confirmed"* copy is therefore optimistic.
    - **Recommendation:** Step 5 should have a distinct "Awaiting payment confirmation" variant for the BT path, with the bank-transfer instructions block and a status-pending banner instead of the receipt block. Already partially shown in the mockup as the bank-transfer instructions variant, but the wording needs softening.

15. **Cancellation policy display:**
    - T&C section 7 shows the cancellation tiers as fixed text. Spec has `CancellationPolicy.tiers` as JSON config (`product-design/01-domain-model.md:369-372`) snapshotted onto the booking. **The T&Cs body should render the policy's tiers dynamically** (templated from `Booking.cancellation_policy.tiers`), not be hardcoded in the version body — otherwise a policy change requires a new `TermsVersion` even though the policy is separately versioned.
    - **Recommendation:** Templated `TermsVersion.body_markdown` with placeholders that the renderer fills from the booking's snapshotted policy.

16. **What does Step 1's "I have reviewed and agree" checkbox actually bind to?**
    - It's not the T&C acceptance (that's Step 3). It's a softer summary-correct acknowledgement.
    - **Recommendation:** Persist as `TermsAcceptance(kind='summary')` with a snapshot of the booking summary JSON in `metadata`. Useful for disputes (*"the guest confirmed the dates and party size before paying"*).

---

## Appendix A — Verbatim string inventory (for FE / translation)

Key strings the SPA must own:

- *"Dear Mr Wood,"* (templated salutation)
- *"I have reviewed and agree to the Booking Summary above."*
- *"The Payer for this booking is different from the Lead Guest"*
- *"I agree to Villa Collective's Privacy Policy and consent to my personal data — and that of any additional guests I have added — being processed for the purposes of fulfilling this booking."*
- *"Add the rest of your party so they can receive the information you choose…"*
- *"+ Add a guest"*
- *"I have read and agree to the Booking Terms and Conditions."*
- *"Important: Prior to making payment, the Lead Guest is responsible for ensuring the party has adequate travel insurance for this booking."*
- *"Pay by Card via Flywire →"* / *"Pay by Bank Transfer via Flywire →"*
- *"no auto-charge — every payment requires your action"*
- *"Having trouble using the online payment system? Call us…"*
- *"Thank you, Ben — your stay is confirmed"* (templated; bare given-name)
- *"Your Villa Collective portal is now live — manage concierge requests, payments, messages, and documents in one place."*
- *"Open my Villa Collective portal →"*
- *"Thank you for choosing Villa Collective — we look forward to arranging a memorable stay for you."*
- *"I'VE SENT THE TRANSFER"* (Flywire widget — outside our control if embedded)

## Appendix B — Cross-document file:line index

For quick navigation during build:

- `workflows/07-enquiry/enquiry-intake.md:1-57` — pre-funnel intake (absent from mockup)
- `workflows/08-quotation/lifecycle.md:23-25` — self-service quote-accept `[STUB]`
- `workflows/08-quotation/lifecycle.md:54-58` — quote expiry `[STUB]`
- `workflows/08-quotation/transmission.md:1-37` — sending the quote (absent from mockup)
- `workflows/09-booking/booking-creation.md:7-9` — staff-driven booking creation trigger
- `workflows/09-booking/booking-creation.md:46-70` — payment schedule generation step
- `workflows/09-booking/booking-creation.md:62-65` — legacy `BookingUrl` (Flywire-hosted) field
- `workflows/09-booking/payment-schedule.md:1-46` — 3-tier schedule generation
- `workflows/09-booking/payment-schedule.md:21-23` — full-payment short-circuit
- `workflows/09-booking/booking-confirmation.md:1-49` — owner approval (separate from guest funnel)
- `workflows/10-payment/checkout-flow.md:1-43` — legacy `SaveCheckoutInfo` shape
- `workflows/10-payment/payment-collection.md:1-99` — Flywire webhook & tokenization paths
- `workflows/10-payment/payment-preauth.md:1-39` — SD pre-auth `[DISABLED]`
- `workflows/10-payment/payment-preauth.md:42-83` — recurring charge `[DISABLED]`
- `workflows/11-integrations/flywire-gateway.md:1-44` — Flywire integration summary
- `product-design/01-domain-model.md:200-208` — `Booking` entity fields
- `product-design/01-domain-model.md:217-223` — `Booking.status` enum
- `product-design/01-domain-model.md:225-230` — `ConciergeLineItem`
- `product-design/01-domain-model.md:245-248` — `TermsVersion`
- `product-design/01-domain-model.md:296-301` — `Guest` entity
- `product-design/01-domain-model.md:312-313` — `MagicLink` entity
- `product-design/01-domain-model.md:321-340` — `DepositPaymentTrack`, `BalancePaymentTrack`, `SecurityDeposit`
- `product-design/01-domain-model.md:342-348` — `PaymentEvent`
- `product-design/01-domain-model.md:369-372` — `CancellationPolicy`
- `product-design/01-domain-model.md:381-384` — `EmailLog`
- `product-design/01-domain-model.md:419-420` — `AuditLog`
- `product-design/03-workflows.md:133-192` — flow 3 (convert quotation to booking)
- `product-design/03-workflows.md:194-225` — flow 4 (direct booking creation, staff-driven)
- `product-design/03-workflows.md:292-346` — flow 6 (take deposit payment, staff-driven)
- `product-design/03-workflows.md:349-381` — flow 7 (rental balance)
- `product-design/03-workflows.md:386-425` — flow 8 (security deposit)
- `product-design/04-rest-api-surface.md:584-590` — `/checkouts` dropped in favour of `/payments?purpose=…`
- `product-design/04-rest-api-surface.md:806-810` — `/terms-versions` endpoints
