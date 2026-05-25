# Client Portal — Mockup Analysis

> **STATUS: DEPRIORITISED (out of v1).** The client portal has no analog in the legacy `ResSystem/` and is ~80% greenfield. See `../10-decisions.md` "Deferred" table. This document is preserved as reference for a future v2 discussion; do **not** implement against it without re-opening the decision.
>
> Source: https://vc-customer-portal.netlify.app/ (single-file React mockup, inline `BOOKING`, `PAYMENT_SCHEDULE`, `CONCIERGE_EXTRAS_INIT`, `INITIAL_MESSAGES`, `CONCIERGE_SERVICES`, `CHECKIN_INFO`, `SERVICE_CATEGORIES` constants)
> Reviewed against: `django_res_design/workflows/`, `django_res_design/product-design/`
> **Headline:** This portal is largely greenfield. The legacy ResSystem `.NET` app has no real guest portal (the only "guest" surface was a checkout form on WordPress — see `workflows/10-payment/checkout-flow.md:8`). The product-design docs spec an **owner** portal (`product-design/02-frontend-design.md:727` §7.3, `product-design/05-improvements-over-original.md:98` §15) but no guest portal. Roughly **80 % of the mockup is brand-new functionality** and **none of it has a corresponding backend in the current spec**.

---

## 1. Summary

The mockup is a self-service portal a confirmed Villa Collective guest opens to manage their booking. After a lightweight email-plus-booking-reference login, they land in a single booking shell with six tabs:

1. **Overview** — booking facts, invited-co-traveller list, service tier card, payment summary mini-table.
2. **Payments** — rental payment schedule (deposit / balance / security deposit) plus a parallel "Additional Services & Concierge Extras" table with a guest-approval step before invoice.
3. **Messages** — Villa Collective → guest broadcast inbox, with acknowledge + reply.
4. **Requests** — guest-initiated service-request tickets (a four-step wizard creates them).
5. **Check-in** — arrival pack (address, codes, WiFi, emergency contact). Sensitive fields are time-locked until arrival day.
6. **Concierge** — read-only "what we've arranged for you" list with expandable notes from the operator.

**Headline coverage estimate.** Cross-referencing every model and endpoint in `product-design/01-domain-model.md` and `product-design/04-rest-api-surface.md`:

- **Direct overlap (~20 %):** `Booking` header data, `DepositPaymentTrack` / `BalancePaymentTrack` / `SecurityDeposit` rows, `ConciergeLineItem` rows, Flywire handoff.
- **Net-new (~80 %):** guest authentication (email + booking ref, not magic-link or password), co-traveller invitations, guest-facing Messages with ack/reply, ticketed service requests with state machine and threaded replies, twelve-category service taxonomy, guest-approval workflow on concierge quotes, time-locked check-in fields, in-portal upgrade-tier request, fee-free service categories.

**Top 5 "this is new" callouts:**

1. **A guest-facing identity surface that isn't a `User`** — login is by `(email, booking_reference)`, with no password or magic link. Nothing in `product-design/01-domain-model.md` §6 supports this; `MagicLink` (`01-domain-model.md:312`) is owner-only.
2. **Co-traveller invites** — `Sarah Cookson`, `James Cookson` shown as invited, with statuses `invite-sent` / `viewed` / `pending` and a "Revoke access" affordance. Zero coverage in current models or APIs.
3. **Guest-approval on concierge quotes** — the "Quoted → Approved → Invoiced → Paid" workflow on `CONCIERGE_EXTRAS_INIT` puts the guest in the loop *between* the operator's price quote and the Flywire invoice. The current `ConciergeLineItem.payment_status` (`01-domain-model.md:230`: `awaiting` / `sent` / `paid` / `failed` / `included` / `refunded`) has no `quoted`-awaiting-guest-approval state.
4. **Ticketed service requests** — `Requests` tab is a full helpdesk-style ticketing surface with a four-step wizard, twelve categories with bespoke per-category field sets, urgency `low/normal/high/urgent`, contact-preference `portal/email/phone/whatsapp`, and threaded `client`/`vc` replies. No `ServiceRequest`/`Ticket` model exists in `01-domain-model.md`.
5. **Time-locked check-in pack** — `Address`, `Directions`, `Entry Codes`, `WiFi`, `Emergency Contact` are gated behind `arrivalReached === true` (computed by comparing today's date to `BOOKING.arrive`). This is a per-field release rule, not a per-record one, and isn't mentioned anywhere in `product-design/` or `workflows/`.

---

## 2. Auth & access model

### 2.1 Login screen

Source: lines 187–203 of the mockup script (`function Login`).

- Title: **"My Booking"**
- Subhead: *"Enter your email address and booking reference to access your booking portal."*
- Two fields: `Email Address` (default `ben@mojomedia.co.uk`), `Booking Reference` (default `VC3345`).
- Primary CTA: **"Access My Booking"**.
- Bottom hint: *"Need help? Call us on +44 (0) 208 950 1588"*.

The mockup's login is a stub (`onLogin` just flips a local state boolean) but the field shape implies the production endpoint: a guest authenticates by demonstrating they know **both** the email on the booking and the booking reference. There is no password field and no second factor.

### 2.2 Conflict with existing auth design

The current spec has three classes of identity:

| Identity | Defined in | Mechanism |
|---|---|---|
| Staff `User` | `01-domain-model.md:303-310` | Password + optional TOTP 2FA, sessions. |
| Owner-portal `Contact`-linked `User` | `01-domain-model.md:312-313` (`MagicLink`) and `04-rest-api-surface.md:101-102` | Passwordless email magic-link → session token. |
| `Guest` | `01-domain-model.md:296-301` | **Has no auth surface at all.** `Guest` has `email`, `phone`, etc. but no `password_hash`, no `MagicLink`, no `UserSession`. |

The portal's email-plus-booking-ref login is therefore a **third, undefined auth flow**. Options the product owner must pick from:

- **(A) Treat the booking reference as a knowledge factor.** Cheap to ship; same security model as airline "manage my booking" flows. Implies a new endpoint, e.g. `POST /auth/guest-portal:login { email, booking_reference }` returning a short-lived JWT scoped to that booking.
- **(B) Use the existing `MagicLink` pattern.** Guest types email; if it matches `Booking.guest.email` or `Booking.payer.email` (or any `CoTravellerInvite.email` — see §5), a magic link is mailed. Stronger; one round-trip slower.
- **(C) Hybrid.** Email + booking ref proceeds to a magic-link gate when the IP / device is unfamiliar.

Whichever direction, the data model needs a `GuestSession` (or extends `UserSession` polymorphically), and the `Guest` entity needs either a `is_portal_enabled` flag or — cleaner — `MagicLink.kind` extended to include `guest_portal`. `01-domain-model.md:387` `CodeAuthLog.kind` is already enumerated as `magic_link / 2fa_code / password_reset` and would similarly need a new value.

### 2.3 Co-traveller invitation mechanism

Source: lines 158–172 of the script and the `Booking Guests` section of the Overview tab.

Initial state seeds two invitees:
```js
{ id: 1, firstName: "Sarah", lastName: "Cookson", email: "sarah@cooksonfamily.com", status: "viewed",      invitedAt: "03 Dec 2025" },
{ id: 2, firstName: "James", lastName: "Cookson", email: "james@cooksonfamily.com", status: "invite-sent", invitedAt: "03 Dec 2025" },
```

The Invite Guest modal (§4.1) lets the lead guest add another row; the row carries a status (`invite-sent` / `viewed` / `pending`), an `invitedAt` date, a **Resend** button (with the explicit tooltip "Resend invite email"), and a **Revoke access** button (`×`).

The empty-state copy is precise about scope: *"Add others travelling with you. They'll receive an email with a private link to view this booking — they can see arrival info, the property, and the concierge plan, but cannot make payments or changes."*

This implies a new `CoTravellerInvite` entity (or similar), with its own state machine and its own scoped session: an invitee's portal view is a **subset** of the lead guest's view (no Payments tab, no Requests/wizard, no Invite Guest action). See §5 and §7.

---

## 3. Tab-by-tab specification

The persistent booking header (lines 187–216) sits above every tab and shows:
- `BOOKING.ref` (`"VC3345"`)
- `BOOKING.property` ("Villa Elysian"), linked to `https://www.villacollective.com/villa/villa-elysian`
- `BOOKING.location` ("Corfu, Greece")
- A status pill (`status-confirmed` / `status-pending`) with label "Confirmed" or "Pending"
- A tier badge ("Signature Service" with a star icon, or "Quintessential Service" with a hands icon)
- "Your Stay: 16 May 2026 – 23 May 2026 · 7 nights · 10 adults, 2 children"
- A four-stat row: **Total Value** (`€14,200`), **Paid** (`€4,260`), **Balance — Due 30 Mar 2026** (`€9,940`), **Concierge** (`"6 services"` — `CONCIERGE_SERVICES.length`).

The tab bar (lines 218–229) carries unread/new badges on **Messages** and **Requests** only. Tab order: `Overview, Payments, Messages, Requests, Check-in, Concierge`.

### 3.1 Overview tab

Source: `function TabOverview`, lines 239–321.

Sections in order:

1. **Villa gallery** — `VILLA_IMAGES` (empty in the mockup; the production version would carry hero shots from `PropertyImage` rows, role-tagged per `01-domain-model.md:60`).
2. **Booking Details table** — rows for `Booking Reference`, `Property` (linked), `Arrival`, `Departure`, `Duration`, `Party Size`, `Maximum Occupancy`, `Check-in`, `Check-out`, `Your Manager` (`"Mya Bass — +44 (0) 208 950 1588"`). Right-aligned link `"↗ View villa on our website"`.
3. **Booking Guests** — see §2.3 above.
4. **Service Level Card** — see §4.4 for the upgrade modal it spawns.
5. **Payment Summary** — a compact two-column table: `Total Rental` / `Paid to Date`, then a row per `PAYMENT_SCHEDULE` entry with two-line cells (amount + status; the Security row carries the extra subtle `"Invoiced separately ~14 days before arrival"`), and a final `Outstanding Balance` row.

**Spec coverage:**

- `Booking Details` rows map cleanly to `Booking` fields in `01-domain-model.md:200-208` (`reference`, `property`, `from_date`, `to_date`, `adults`, `children`, etc.). One unmapped field: `BOOKING.maxOccupancy = 10` — `01-domain-model.md:57` lists `max_occupancy` as a derived `Property` field, so this surface needs to expose it through whatever read serializer powers the portal.
- "Your Manager" maps to `Booking.assigned_to` (`01-domain-model.md:202`) — the spec's *internal* staff owner. The portal exposes `User.first_name + last_name`, `User.email` (used in the Concierge tab — §3.6), and a phone number. **`User` has no phone field** in `01-domain-model.md:303-310`; either staff need a phone column or the portal exposes a generic VC duty number.
- "View villa on our website" assumes a public-website URL pattern `https://www.villacollective.com/villa/{Property.slug}` (`01-domain-model.md:57` `slug`). That's a hard dependency on the WordPress outbound publish path (`integrations.SyncRecord` with `provider=WORDPRESS_SITE`, see `01-domain-model.md:31-33`); the URL is *not* a backend-served route.

**Implied backend behaviour:**

- A read endpoint, e.g. `GET /portal/booking` (scoped to the session), returning a tailored shape: hero images, manager contact card, payment summary, invited co-travellers, current service tier. This is **not** the operator-facing `GET /bookings/{id}` from `04-rest-api-surface.md:451` — fields like `assigned_to.phone`, `maxOccupancy` derivation, and co-traveller list aren't on that endpoint.

### 3.2 Payments tab

Source: `function TabPayments`, lines 324–405.

Two parallel tables, separated by an "Additional Services & Concierge Extras" section title:

#### Table A — Villa Rental — Payment Schedule

Columns: `Description`, `Amount`, `Due Date`, `Status`, *(action)*.

Rows come from `PAYMENT_SCHEDULE` (line 348):
```js
[
  { desc: "Deposit (30%)",     amount: "€4,260", due: "02 Dec 2025", status: "paid",     paidDate: "02 Dec 2025", method: "Bank Transfer" },
  { desc: "Balance",           amount: "€9,940", due: "30 Mar 2026", status: "due",      paidDate: null,           method: "Bank Transfer" },
  { desc: "Security Deposit",  amount: "€1,420", due: "16 May 2026", status: "upcoming", paidDate: null,           method: "Bank Transfer" },
]
```

Per-row actions:
- `status === "due"` → **"Pay Now"** button (opens the Flywire handoff modal — §4.3).
- `status === "upcoming"` → grey text **"Not yet open"**.
- `status === "paid"` → secondary line "Paid 02 Dec 2025" inside the Description cell.

Status pills colour-coded:
- `p-paid` (green)
- `p-due` (amber)
- `p-upcoming` (grey)

**Spec coverage:**
- Maps to `DepositPaymentTrack` (`01-domain-model.md:321`), `BalancePaymentTrack` (`01-domain-model.md:326`), `SecurityDeposit` (`01-domain-model.md:331`). The three-track model is exactly what `product-design/05-improvements-over-original.md:147` calls correct from the legacy system.
- The status enum is reduced for the guest: `paid / due / upcoming` instead of the backend's `awaiting / link_sent / viewed / paid / partially_paid / failed / waived / refunding / refunded / overdue` (`01-domain-model.md:324, 330, 336-338`). The portal must collapse those — see §7.
- The Security Deposit row's note *"Invoiced separately ~14 days before arrival"* implies a `due_at` minus 14d release rule. `SecurityDeposit.due_at` exists (`01-domain-model.md:334`). The 14-day pre-arrival timing is **not currently captured** in `PropertyFinance.security_deposit_*` (`01-domain-model.md:71`); add either a `days_before_arrival` field or read it from `SystemDefaults`.

**Implied backend behaviour:**
- The guest-portal Payments read collapses three track tables into a single ordered list with a uniform status enum.
- "Pay Now" creates a Flywire `PaymentRequest` against the relevant `PaymentTrack`. This is the **inbound** half of `workflows/11-integrations/flywire-gateway.md:18` — i.e., the previously `[DISABLED]` outbound `/commercial/v1/payment-requests` call must be **re-enabled** for guest-initiated payment. `workflows/11-integrations/flywire-gateway.md:39` already lists this under "Open design questions: Re-enable or remove".

#### Table B — Additional Services & Concierge Extras

Columns: `Service`, `Amount`, `Reference`, `Status`, *(action)*.

Rows come from `CONCIERGE_EXTRAS_INIT` (line 354):
```js
{ id: "e1", service: "Airport Transfer (Arrival)",      detail: "Corfu Airport → Villa Elysian · 16 May · 12 pax",      amount: "€280",   status: "paid",     paidDate: "02 Dec 2025", invoiceRef: "VCX-001" },
{ id: "e2", service: "Private Chef — Dinner Service",   detail: "Chef Elena · 7 evenings · 16–22 May",                    amount: "€2,100", status: "invoiced", invoiceRef: "VCX-002", invoiceDate: "28 Apr 2026" },
{ id: "e3", service: "Grocery Welcome Pack",            detail: "Pre-arrival provisions · 16 May",                        amount: "€320",   status: "invoiced", invoiceRef: "VCX-003" },
{ id: "e4", service: "Car Hire — 2× Jeep Wrangler",     detail: "16–23 May · Hertz Corfu",                                amount: "€980",   status: "quoted",   invoiceRef: null },
{ id: "e5", service: "Boat Day Trip — Ionian Explorer", detail: "Full day island hopping · 19 May · 12 pax",              amount: "€1,200", status: "quoted",   invoiceRef: null },
{ id: "e6", service: "Spa & Massage Therapist",         detail: "In-villa · 2× 60 min sessions · 20 May",                 amount: "€260",   status: "quoted",   invoiceRef: null },
```

Status enum (`statusLabel` map, line 331):
- `quoted` → **"Awaiting Approval"** (yellow). Action: **"Approve"** button (line 383).
- `approved` → **"Approved"** (greyed). Action: "Awaiting invoice".
- `invoiced` → **"Invoice Ready"** (blue). Action: **"Pay Now"** (Flywire modal).
- `paid` → **"Paid"** (green). Action: "Paid 02 Dec 2025".

Footer summary cells: `Awaiting Approval €totalQuoted`, `Invoiced — Payable €totalInvoiced`, `Paid to Date €totalPaid`. Footnote: *"All additional service charges are confirmed with you before being invoiced. Payments are processed via Flywire alongside your rental balance."*

A tier badge ("Quintessential" / "Signature") sits in the section header.

**Spec coverage:**
- The line-item shape maps loosely to `ConciergeLineItem` (`01-domain-model.md:225-230`).
- **The status workflow does not match.** `ConciergeLineItem.payment_status` is `awaiting / sent / paid / failed / included / refunded`. The portal's `quoted → approved → invoiced → paid` four-state flow is a different model: it inserts an explicit *guest-approval gate* between operator quote and Flywire invoice. Two options for reconciliation:
  - (a) Rename / extend `ConciergeLineItem.payment_status` to `quoted / approved / sent_for_payment / paid / failed / cancelled / included / refunded`.
  - (b) Add an upstream `ConciergeLineItem.approval_status` (`pending / approved / declined`) orthogonal to payment status, and gate the payment-link send on `approval_status == approved`.
  - Option (b) cleanly separates "guest said yes" from "money moved" and matches `product-design/05-improvements-over-original.md:94-95` §14, which already calls out per-line state. Recommend (b).
- The `invoiceRef` field (`"VCX-001"`) is **net new**. No `Invoice` model exists in `01-domain-model.md` — concierge charges currently flow straight to `PaymentEvent`. Either expose `PaymentEvent.external_reference` (`01-domain-model.md:345`) as `invoiceRef`, or introduce a thin `Invoice` row that batches one or more `ConciergeLineItem` rows under a single document reference.

**Implied backend behaviour:**
- `POST /portal/extras/{id}:approve` transitions `quoted → approved`.
- An operator action `POST /bookings/{id}/concierge/{id}:invoice` transitions `approved → invoiced` and assigns `invoiceRef`.
- "Pay Now" on an `invoiced` row spawns one Flywire request scoped to that single line item.
- The empty-state isn't shown, but the table should support zero rows gracefully (the Concierge tab — §3.6 — has both pending and approved-by-default services visible).

### 3.3 Messages tab

Source: `function TabMessages`, lines 408 to ~445 plus the rendered detail in `sect3.txt:1-32`.

#### List view
Each message row shows:
- "Villa Collective / {sender}" header (prefixed `"● New — "` when `unread === true`).
- Date string in `"08 Dec 2025, 14:15"` form.
- Subject, body preview (first non-empty line, fallback to first 100 chars).
- Right-aligned: `✓ ACK'D` flag, reply count (`"2 replies"` / `"1 reply"`).

Three seeded messages (`INITIAL_MESSAGES`, line 363):
1. `"Pre-Arrival Information — Villa Elysian"` from `Mya Bass`, 14 Jan 2026 — **unread**, **not acknowledged**.
2. `"Your Booking Confirmation — VC3345"` from `Mya Bass`, 08 Dec 2025 — **read**, **acknowledged**.
3. `"Deposit Payment Received — VC3345"` from `Accounts`, 02 Dec 2025 — **read**, not acknowledged.

#### Detail view
- Header strip: `"From Villa Collective — {sender}"` + date.
- Subject as heading.
- Body rendered with `whiteSpace: "pre-line"`.
- Replies (`{ from: "client", name, date, text }`) below in `reply-item` rows.
- Two CTAs: **"✓ Acknowledge"** (one-shot, disappears once acknowledged) and **"↩ Reply"** (toggles a textarea + **"Send Reply"** button).
- Acknowledgment shows as `"✓ Acknowledged"` badge.

**Spec coverage:**
- Closest existing entity is `EmailLog` (`01-domain-model.md:381`). But `EmailLog` is **transactional outbound** with delivery-tracking states (`queued / sent / delivered / opened / bounced / failed`); it is not a *threaded* surface the guest reads in-portal and replies to.
- The mockup makes Messages a true two-way inbox: VC writes, the guest reads, the guest replies, the message can be `acknowledged`. None of this is in the current data model. See §5 for the implied `Thread` / `Message` shape.

**Conflict with existing specs:** `05-improvements-over-original.md` doesn't mention guest-facing comms at all; the only comms section in `product-design/04-rest-api-surface.md:666` is operator-facing email templates and log. **Two distinct surfaces are needed**: outbound transactional emails (which the EmailLog covers) and a *separate* two-way Threaded conversation that mirrors selected emails into the portal and accepts in-portal replies.

#### Implied backend behaviour
- An inbox endpoint `GET /portal/messages` returning a list per `unread`, `acknowledged`, reply count.
- `POST /portal/messages/{id}:acknowledge` flipping a boolean.
- `POST /portal/messages/{id}/replies { body }` appending a reply.
- An operator-side surface where Mya / Accounts compose the initial message; this is **not** the existing operator booking timeline, it is a deliberate guest-facing channel.
- Reconciliation question: does an operator's outbound email automatically create a portal-visible Message, or are the two channels independent? See §8 open questions.

### 3.4 Requests tab

Source: `function TabRequests`, lines 36–79 of `sect3.txt`. Starts empty (`requests = []`). Populated by the Request Service wizard (§4.2).

#### List view
- **My Service Requests** header with a **"+ New Request"** button.
- Empty state: large `📋` emoji + `"No requests yet."` + `"Use the button above to arrange additional services for your stay."`
- Per-ticket card: title (the service category label, e.g. `"Boat & Water"`), meta line `"REQ-1234 · Submitted {date} · {urgency label}"` where the urgency label is `"⚡ Urgent"` / `"High priority"` / `"Normal"`.

#### Status enum
```js
new        → "New"          (badge: t-new)
in_progress → "In Progress" (badge: t-inprogress)
resolved   → "Resolved"     (badge: t-resolved)
```

#### Detail (expanded ticket)
- Threaded conversation (`req.thread = [{ from: "client" | "vc", time, text }]`).
- Inline reply textarea + **"Send Message"** (disabled while ticket is `resolved`).
- The initial thread message is auto-built from the wizard's form data as `"{label}: {value}\n..."`.

#### The implicit fields per ticket
From the wizard (§4.2):
- `id`: pattern `"REQ-" + 4-digit-random`.
- `service`: category label.
- `icon`: emoji (`SERVICE_CATEGORIES`, line 401).
- `urgency`: `low | normal | high | urgent`.
- `contactPref`: `portal | email | phone | whatsapp`.
- `formData`: keyed dict of category-specific fields.
- `date`: ISO-formatted submission timestamp.
- `status`: starts `new`.
- `thread`: starts with one client message containing the form summary.

**Spec coverage:** Zero. There is no `ServiceRequest` / `Ticket` / `Thread` / `Message` model anywhere in `01-domain-model.md`. This is a brand-new domain.

**Implied backend behaviour:**
- New entities (see §5): `ServiceRequest`, `ServiceRequestThread`, `ServiceRequestMessage`.
- `POST /portal/requests` to create; `POST /portal/requests/{id}/messages` to reply.
- Operator-side surface to triage tickets and update status — this is a **new operator screen** beyond what `product-design/02-frontend-design.md:524` §3.14 describes (existing Concierge surface is operator-driven line items, not a guest-driven inbox).
- Implied SLA promise in the wizard's step 3 footer: *"Your request will be reviewed by {manager} who will respond within 2–4 hours during business hours."* This sets product expectations the system needs to be able to meet (escalation logic? after-hours mode?).

### 3.5 Check-in tab

Source: `function TabCheckin`, lines 82–114 of `sect3.txt`.

#### Info banner
*"ℹ️ Check-in details are confirmed. Your villa manager **Kostas** will greet you on arrival. Check-in is from **16:30 on 16 May 2026**."*

#### Grid of nine info boxes (`CHECKIN_INFO`, line 378)
| Field | Locked pre-arrival? | Sample value |
|---|---|---|
| `Check-in` | no | `"16:30 on 16 May 2026"` |
| `Check-out` | no | `"10:30 on 23 May 2026"` |
| `Address` | **yes** | `"Villa Elysian, Agios Stefanos, Corfu 49081, Greece"` |
| `Directions` | **yes** | Driving directions, 3 sentences |
| `Entry Codes` | **yes** | `"Gate code: 4821 — Key safe code: 7734"` |
| `WiFi` | **yes** | `"Network: VillaElysian_Guest — Password: elysian2026"` |
| `Parking` | no | `"Ample private parking available within the villa gates."` |
| `Emergency Contact` | **yes** | `"Kostas Papadopoulos — +30 694 123 4567 (08:00–22:00 local time)"` |
| `Nearest Hospital` | no | `"Corfu General Hospital — +30 2661 360400 — 28km"` |

Locked-field placeholder copy (line 89): *"Released on the day of arrival (16 May 2026) for security. You'll see the details here as soon as your check-in day begins."* with a `🔒 LOCKED` pill.

#### Arrival Notes section
Free-text from `CHECKIN_INFO.notes`: *"Your villa manager Kostas will greet you on arrival. Please bring a copy of your booking confirmation. Grocery delivery has been arranged for 17:00 on your arrival day."*

**Spec coverage:**
- `Property.address_*` fields exist (`01-domain-model.md:57`).
- A `PropertyDescription` row with `section = "villa_info"` could carry directions / parking / nearest hospital. But the schema currently lists `section` enum as `overview / house_rules / villa_info / further_info` (`01-domain-model.md:62`) — `villa_info` is the right bucket but the granularity is single rich-text per section, not the **per-field** structure the portal shows.
- WiFi credentials, gate codes, key-safe codes are **not** in `Property` or `PropertySettings`. Nothing in `01-domain-model.md:67-71` carries them. Add either a `PropertyArrivalPack` 1:1 sibling of `PropertySettings`, or a `BookingArrivalPack` 1:1 sibling of `Booking` (the latter is more flexible: codes can rotate per stay).
- The **time-locking** logic is a portal-side gate. Backend can stay simple: always return the data; the portal compares "now" against `Booking.from_date` (in `Property.timezone` — `01-domain-model.md:42`) and hides locked fields. **OR** — the more security-conscious option — the backend serves a redacted shape until the release window opens. The mockup comment at line 86 says *"In production this is computed by comparing today's date to BOOKING.arrive"* — implying client-side gating, which is **insufficient** for credentials of this sensitivity. Recommend backend redaction.

### 3.6 Concierge tab

Source: `function TabConcierge`, lines 117–149 of `sect3.txt`.

Layout: a list of expandable rows backed by `CONCIERGE_SERVICES` (line 369):

| Service | Status | Notes (truncated) |
|---|---|---|
| Airport Transfer | `confirmed` | Driver Nikos, holding VC sign, 12-seat Mercedes Sprinter… |
| Private Chef | `confirmed` | Chef Elena, daily dinner 16–22 May… |
| Car Hire | `pending` | Awaiting Hertz Corfu confirmation… |
| Boat Day Trip | `arranged` | "Independently arranged directly with Ionian Explorer." |
| Grocery Pack | `confirmed` | Welcome pack incl. milk, eggs, bread, beer ×24… |
| Massage Therapist | `pending` | Confirming with preferred therapist… |

Status enum (`statusLabel` map, line 120):
```js
confirmed → "Confirmed"               (badge: c-confirmed, green)
pending   → "Pending"                 (badge: c-pending, amber)
arranged  → "Arranged Independently"  (badge: c-arranged, blue/grey)
```

Each row expands to show `notes` from the operator (rich plain text). A "+ Request a Service" button in the section header opens the same Request Service wizard as the Requests tab.

A second section at the bottom — **Your Manager** — repeats the manager card with rows `Name`, `Email`, `Phone`, `Available` (`"08:00 – 22:00 local time"`).

**Spec coverage:**
- Maps to `ConciergeLineItem` (`01-domain-model.md:225-230`). The display columns are mostly there: `name`, `description` (rich text), `scheduled_at`, `confirmed_at`, `notes`.
- The **`arranged`** status is new. `ConciergeLineItem.payment_status` (`01-domain-model.md:230`) has `awaiting / sent / paid / failed / included / refunded`. None of those means "guest arranged this themselves — operator just tracking it for context". The `Boat Day Trip` row carries `status: "arranged"` and `payment_status` is irrelevant. Recommend either (a) adding `"arranged_externally"` to the payment-status enum and treating it as a no-charge terminal state, or (b) splitting the concierge state into two: `arrangement_status` (`pending / confirmed / arranged / cancelled`) and `payment_status` (`awaiting / sent / paid / included / refunded`). Recommend (b); echoes the same split proposed for the Payments-tab extras in §3.2.

**Implied backend behaviour:**
- `GET /portal/concierge` (sub-resource of the booking) returning the list with `arrangement_status` + per-item `notes` (rich text, sanitised; see `product-design/02-frontend-design.md:597-602` for the existing Tiptap policy).
- The `+ Request a Service` action goes via the Requests pipeline (§3.4), not directly into a new `ConciergeLineItem`. A request can be **promoted** to a `ConciergeLineItem` once the operator accepts/quotes/invoices it. That's a new state transition spanning two new entities.

---

## 4. Modals & wizards

### 4.1 Invite Guest modal

Source: `function InviteGuestModal`, lines 8–43 of `sect2.txt`.

- Title: **"Invite a Guest"**, sub: *"Send a private link to view this booking"*.
- Body copy: *"We'll email this person a private link to view the booking. They can see the property, arrival info and concierge plan, but cannot make payments or changes."*
- Fields: `First name`, `Last name`, `Email address`. Validation: all three non-empty; email regex `\S+@\S+\.\S+`.
- Footer: **Cancel** / **Send invite** (`Send invite` disabled until valid).

**Implied entity:** `CoTravellerInvite` with fields `booking_id`, `first_name`, `last_name`, `email`, `invited_at`, `invited_by`, `status` (`invite_sent / viewed / pending / revoked`), `invite_token` (signed), `last_resent_at`. Soft-delete forbidden (`CLAUDE.md`); revocation is a hard delete + `AuditLog` entry, or a `status = revoked` terminal state with an `archived_at`.

### 4.2 Request Service wizard (4 steps, 12 categories)

Source: `function RequestServiceModal`, lines 45–185 of `sect2.txt`.

#### Wizard chrome
- Reference number generated client-side at mount: `"REQ-" + Math.floor(1000 + Math.random() * 9000)`.
- Modal backdrop can't be dismissed by click-outside on the final confirmation step (lines 89).
- Each step has a `"Step N of 3"` label in the footer (despite there being a fourth confirmation panel).

#### Step 1 — Category

The tier-context bar shows the current `BOOKING.serviceLevel` badge. Below it, a coloured note:
- If Signature: *"Your dedicated concierge will handle arrangements. Costs for services (chefs, hire, etc.) are confirmed in advance and billed separately."*
- If Quintessential: *"We'll arrange this on your behalf and send a quote for approval before proceeding. Charges appear in your Extras & Additional Services."*

The 12 service categories (`SERVICE_CATEGORIES`, line 401) — each is a tile with an emoji + SVG icon + label:

| `id` | icon | label |
|---|---|---|
| `transfer` | 🚗 | Transfers & Taxi |
| `chef` | 👨‍🍳 | Private Chef |
| `car` | 🚙 | Car Hire |
| `boat` | ⛵ | Boat & Water |
| `grocery` | 🛒 | Grocery Pack |
| `spa` | 💆 | Spa & Wellness |
| `wine` | 🥂 | Wine & Champagne |
| `activities` | 🏄 | Activities |
| `restaurant` | 🍽️ | Restaurant |
| `shopping` | 🛍️ | Shopping & Personal |
| `flights` | ✈️ | Flight Assistance |
| `other` | 📋 | Other Request |

#### Step 2 — Details (per-category form schema)

The `getServiceFields(id)` function (line 95) returns a bespoke form per category. Across all 12 categories, the union of fields is:

| Field key | Categories | Type | Sample placeholder |
|---|---|---|---|
| `pickup` | transfer | input | "e.g. Corfu Airport" |
| `dropoff` | transfer | input | "e.g. Villa Elysian" |
| `date` | transfer, boat, grocery, spa, activities, restaurant, shopping | input or `type=date` | "e.g. 16 May 2026, 15:00" |
| `pax` | transfer, boat | input | "e.g. 10" |
| `flight` | transfer | input | "e.g. EasyJet EZY8765" |
| `dates` | chef, car, flights | input | "e.g. 16–22 May" |
| `guests` | chef, spa, restaurant | input | "e.g. 12" |
| `dietary` | chef, grocery, restaurant | textarea | "e.g. 2 vegetarian, 1 nut allergy" |
| `cuisine` | chef, restaurant | input | "e.g. Mediterranean, Greek" |
| `vehicles` | car | input | "e.g. 2" |
| `type` | car, boat | input | "e.g. 4x4 / SUV / automatic" |
| `drivers` | car | input | "e.g. 2" |
| `duration` | boat | input | "Full day / Half day" |
| `treatment` | spa | input | "e.g. Swedish massage / couples massage" |
| `items` | wine | textarea | "e.g. 2x bottles Moët, 1x case of local red wine" |
| `occasion` | wine | input | "e.g. Birthday celebration" |
| `activity` | activities | input | "e.g. quad biking / cooking class / hiking" |
| `participants` | activities | input | "e.g. 6" |
| `ages` | activities | input | "e.g. 30–55, adults only" |
| `request` | shopping | textarea | "Describe your request in as much detail as possible" |
| `route` | flights | input | "e.g. London to Corfu, return" |
| `passengers` | flights | input | "e.g. 12" |
| `class` | flights | input | "e.g. Business / Economy" |
| `subject` | other | input | "Brief description of your request" |
| `details` | other | textarea | "Please describe your request in as much detail as possible" |
| `notes` | all (except `shopping`, `other`) | textarea | "Additional Notes" |

This is essentially a *category-specific JSON form schema*. Two design options:

- **(A)** Bake the schema into the SPA, send a flat `formData` blob. Backend stores `ServiceRequest.payload` as JSONField, `category` as enum. Simple; loses operator-side query and reporting.
- **(B)** Expose `ServiceRequestCategory` as a managed taxonomy with a `field_schema` JSON column. Operators can add categories and tweak fields without a deploy. More backend, but more flexible.

The 12 categories above are stable enough that (A) seems right for v1, with an explicit JSONField (well-typed via Pydantic / Zod). See §5.

#### Step 3 — Priority + contact preference + free-text

Urgency (`urgencies`, line 86):
```js
{ id: "low",     label: "Low – no rush" },
{ id: "normal",  label: "Normal" },
{ id: "high",    label: "High – needed soon" },
{ id: "urgent",  label: "Urgent – ASAP" },
```

Contact preference (`contacts`, line 87):
```js
{ id: "portal",   label: "Via this portal" },
{ id: "email",    label: "Email me" },
{ id: "phone",    label: "Call me" },
{ id: "whatsapp", label: "WhatsApp" },
```

Plus a `_extra` textarea ("Anything Else We Should Know?") and a coloured footer with the SLA promise: *"Your request will be reviewed by **{BOOKING.manager}** who will respond within 2–4 hours during business hours. Urgent requests will be prioritised."*

#### Step 4 — Confirmation

- Title flips to **"Request Submitted"**.
- ✅ icon, summary card with `Reference`, `Service`, `Priority`, `Response Via` rows.
- Footer copy: *"You will receive a confirmation email shortly. Our team typically responds within 2–4 hours during business hours."*

### 4.3 Pay Now / Flywire handoff modal

Source: lines 398–404 of `sect2.txt`.

Title: **"Make Payment"**. Body: *"You are about to pay **{amount}** for **{description}**. You will be redirected to our secure payment provider, Flywire."*

Two buttons: **"Proceed to Flywire"** (currently a no-op in the mockup) and **"Cancel"**.

**Spec coverage:**
- Flywire is the only gateway (`workflows/11-integrations/flywire-gateway.md:41`: *"Flywire is the payment gateway. No multi-provider abstraction in v1."*).
- The outbound `/commercial/v1/payment-requests` call is currently `[DISABLED]` (`workflows/11-integrations/flywire-gateway.md:20`) — re-enabling it is already an open question (`workflows/11-integrations/flywire-gateway.md:39`).
- HMAC-SHA256 inbound verification is also flagged as an open question on the same doc, line 37.

**Implied backend behaviour:**
- `POST /portal/payments { track_id }` or `POST /portal/extras/{id}:pay` returns a Flywire redirect URL (or a hosted Flywire iframe URL). The legacy WordPress path forwarded directly to Flywire's domain; the new SPA either does the same or embeds Flywire's hosted form.
- The webhook returns to `POST /webhooks/flywire` (`product-design/04-rest-api-surface.md:60`), where the signature must be HMAC-verified (per `workflows/11-integrations/flywire-gateway.md:37`).
- Idempotency on the webhook is already an open question (`workflows/11-integrations/flywire-gateway.md:38`).

### 4.4 Upgrade Service Level (Quintessential → Signature)

Source: `function ServiceLevelCard`, lines 207–237 of `sect2.txt`.

The card has two halves: left (current tier description) and right (upgrade panel, only shown when current tier is Quintessential).

#### Tier copy
- **Quintessential** (default): *"All the essentials for a seamless stay. You can still request any additional service — private chefs, car hire, boat trips, spa treatments and more — which our team will arrange and invoice separately. Upgrade to Signature for proactive, bespoke pre-trip planning."*
- **Signature**: *"Our most comprehensive offering. Your dedicated London-based team proactively plans every detail — crafting a personalised itinerary before you arrive, arranging private chefs, experiences, wellness, and more. Additional service costs are confirmed in advance and billed separately."*

#### Pill lists
Quintessential includes (always shown):
- `"Check-in & Check-out Management"`
- `"Airport Transfer Arrangements"`
- `"In-Villa Support"`
- `"All Additional Services (Arranged & Billed)"`

Signature additionally includes:
- `"Dedicated London-Based Concierge"`
- `"Bespoke Pre-Trip Itinerary"`
- `"Proactive Planning & Booking"`
- `"Private Chef Arrangements"`
- `"Boat & Water Charters"`
- `"Restaurant Reservations"`
- `"Spa & Wellness Bookings"`
- `"Excursions & Experiences"`
- `"Childcare & Security Services"`

#### Upgrade panel (Quintessential-only)
- Headline: **"Upgrade to Signature"**.
- Pricing copy: *"Our Signature team will proactively plan your entire stay — a detailed bespoke itinerary prepared before you arrive, with every arrangement handled. **From approximately €500.**"*
- Button: **"Request Upgrade"** → confirm step → sent state.
- Confirm copy: *"This will send an upgrade request to {manager}. Are you sure you'd like to proceed?"*
- Sent copy: *"Upgrade request sent — {manager} will be in touch."*

**Spec coverage:**
- `Booking.concierge_tier` exists (`01-domain-model.md:202`: `quintessential / signature`).
- `Booking.concierge_price_amount` exists (`01-domain-model.md:202`) — but the mockup uses *"From approximately €500"* as a teaser, not the booking's actual upgrade price. The portal needs to resolve a current-price-to-upgrade — that's either a SystemDefaults read or a per-property override.
- No backend state for "guest has requested an upgrade — operator must action". Two options:
  - Bind the upgrade request into the `ServiceRequest` table with a special category `tier_upgrade`. Cleaner.
  - Add `Booking.concierge_upgrade_requested_at` + a state on Booking. Lighter.

The flow conflicts with `product-design/03-workflows.md:152` flow 6 step 6, which says concierge tier is picked **at booking creation** by the operator. Adding guest-initiated upgrade *post-confirmation* is a new path the booking modification rules (`product-design/03-workflows.md:239`) don't currently cover.

---

## 5. Implied data model additions

These are entities the mockup requires that are absent from `product-design/01-domain-model.md`. Listed in dependency order.

### GuestSession (or extend `MagicLink`)
- Cross-reference: `01-domain-model.md:303` `User`, `01-domain-model.md:312` `MagicLink`.
- Fields: `booking_id` (FK), `email`, `token_hash`, `expires_at`, `created_at`, `last_seen_at`, `ip`, `user_agent`, `scope` (`lead | co_traveller`), `co_traveller_invite_id` (FK, nullable).
- Lifecycle: session-typed; no soft delete. Hard expiry; revocation via revoking the parent invite.

### CoTravellerInvite
- Cross-reference: nothing exists; new entity.
- Fields: `booking_id` (FK), `first_name`, `last_name`, `email`, `invite_token_hash`, `invited_at`, `invited_by` (FK to whichever `GuestSession` or `Guest` issued it), `last_resent_at`, `status` (`invite_sent | viewed | revoked`), `viewed_at` (nullable), `revoked_at` (nullable).
- Lifecycle: per project convention, status enum + dated entry timestamps; no soft delete (`CLAUDE.md` — *"No soft delete"*).

### MessageThread / Message (guest-facing)
- Cross-reference: distinct from `EmailLog` (`01-domain-model.md:381`), which tracks outbound delivery.
- `MessageThread` fields: `booking_id` (FK), `subject`, `created_at`, `last_message_at`, `is_archived`.
- `Message` fields: `thread_id` (FK), `direction` (`vc_to_guest | guest_to_vc`), `sender_kind` (`user | system`), `sender_user_id` (FK, nullable), `body` (rich text), `created_at`, `unread` (computed or per-recipient row in a join table), `acknowledged_at` (nullable — only meaningful for `vc_to_guest`), `email_log_id` (FK to `EmailLog`, nullable — for messages that were also emailed).
- A `vc_to_guest` message can have `acknowledged_at` set when the guest clicks "✓ Acknowledge".
- Reconciliation: should an outbound transactional email automatically create a corresponding Message thread? See §8.

### ServiceRequest
- New entity.
- Fields: `booking_id` (FK), `reference` (e.g. `REQ-1234`), `category` (TextChoices over the 12 IDs), `payload` (JSONField with the bespoke per-category fields), `urgency` (`low | normal | high | urgent`), `contact_preference` (`portal | email | phone | whatsapp`), `additional_notes` (text), `status` (`new | in_progress | resolved | cancelled`), `assigned_to` (FK to `User`, nullable), `created_at`, `resolved_at`, `linked_concierge_item_id` (FK to `ConciergeLineItem`, nullable — populated when the request is promoted to a billable line item).
- Reference format: deterministic 4-digit suffix (mockup uses `Math.random()`, production needs a sequence — fold into `SystemDefaults`).

### ServiceRequestMessage
- New entity. (Or fold into the same Message table with a `subject_kind` discriminator — see §8.)
- Fields: `service_request_id` (FK), `direction` (`client_to_vc | vc_to_client`), `sender_user_id` (FK, nullable), `body` (rich text), `created_at`.

### BookingArrivalPack
- New entity, 1:1 with `Booking`.
- Fields: `booking_id` (FK, unique), `gate_code`, `key_safe_code`, `wifi_ssid`, `wifi_password`, `directions` (rich text override), `parking_notes`, `emergency_contact_name`, `emergency_contact_phone`, `emergency_contact_hours`, `nearest_hospital_name`, `nearest_hospital_phone`, `nearest_hospital_distance_km`, `arrival_notes` (rich text), `manager_user_id` (FK to `User` — the on-site villa manager, possibly distinct from `Booking.assigned_to`).
- Many of these could default from `Property` (e.g. `PropertyArrivalDefaults`), with per-booking overrides. The mockup conflates booking-specific (greeting time, grocery delivery) with property-static (address, nearest hospital).

### ConciergeQuoteApproval (optional)
- Either embed as new fields on `ConciergeLineItem` (`approval_status` enum + `approved_by_guest_at`) or as a separate small row keyed on `ConciergeLineItem.id`. New fields path is simpler.

### TierUpgradeRequest
- Either a `ServiceRequest` with `category = 'tier_upgrade'` (simpler) or a new field on `Booking`.

---

## 6. Implied API surface additions

These are all **guest-scoped** endpoints under a `/portal/` prefix (vs the operator-facing `/bookings`, `/properties`, etc. in `product-design/04-rest-api-surface.md`).

### Auth
| Method | Path | Purpose |
|---|---|---|
| POST | `/portal/auth:login` | Email + booking-ref → short-lived JWT scoped to one booking |
| POST | `/portal/auth:logout` | Invalidate the session |
| POST | `/portal/auth/invite:consume` | Co-traveller exchanges signed token for a scoped session |

These are new — not the magic-link / 2FA / password flows in `04-rest-api-surface.md:86-102`.

### Booking read
| Method | Path | Purpose |
|---|---|---|
| GET | `/portal/booking` | Single shape carrying header, payment summary, invited co-travellers, service tier, manager card |

### Co-travellers
| Method | Path | Purpose |
|---|---|---|
| GET | `/portal/co-travellers` | List |
| POST | `/portal/co-travellers` | Invite |
| POST | `/portal/co-travellers/{id}:resend` | Re-send invite email |
| DELETE | `/portal/co-travellers/{id}` | Revoke |

### Payments
| Method | Path | Purpose |
|---|---|---|
| GET | `/portal/payments` | Rental schedule rows (3 entries: deposit, balance, security) |
| POST | `/portal/payments/{track_id}:initiate` | Returns Flywire redirect URL |
| GET | `/portal/extras` | Concierge extras with `quoted/approved/invoiced/paid` status |
| POST | `/portal/extras/{id}:approve` | Approve a quoted extra |
| POST | `/portal/extras/{id}:pay` | Returns Flywire redirect URL for an invoiced extra |

### Messages
| Method | Path | Purpose |
|---|---|---|
| GET | `/portal/messages` | Inbox list |
| GET | `/portal/messages/{id}` | Detail with thread |
| POST | `/portal/messages/{id}:acknowledge` | Set `acknowledged_at` |
| POST | `/portal/messages/{id}/replies` | Append client reply |

### Service Requests
| Method | Path | Purpose |
|---|---|---|
| GET | `/portal/requests` | List of guest's tickets |
| POST | `/portal/requests` | Create (category + payload + urgency + contact pref) |
| GET | `/portal/requests/{id}` | Detail with thread |
| POST | `/portal/requests/{id}/messages` | Append client message |

### Concierge (read-only for guest)
| Method | Path | Purpose |
|---|---|---|
| GET | `/portal/concierge` | List of arranged services with `confirmed/pending/arranged` status |

### Check-in
| Method | Path | Purpose |
|---|---|---|
| GET | `/portal/checkin` | Returns arrival pack with sensitive fields **redacted** until release time |

### Tier upgrade
| Method | Path | Purpose |
|---|---|---|
| POST | `/portal/tier-upgrade:request` | Lodges the upgrade request (folds into `ServiceRequest` if that route is chosen) |

None of these endpoints exist in `04-rest-api-surface.md`. The closest precedent is the magic-link block at `04-rest-api-surface.md:101-102`, but those are owner-scoped.

---

## 7. Conflicts with existing specs

### 7.1 Status enums collapse / extend asymmetrically

The portal shows reduced status enums that don't map cleanly to backend enums:

| Surface | Portal enum | Backend enum (`01-domain-model.md`) |
|---|---|---|
| Rental payments | `paid / due / upcoming` | `awaiting / link_sent / viewed / paid / partially_paid / failed / waived / refunding / refunded` (`:324, :330`) |
| Concierge extras | `quoted / approved / invoiced / paid` | `awaiting / sent / paid / failed / included / refunded` (`:230`) |
| Concierge services | `confirmed / pending / arranged` | (no equivalent `arrangement_status` — see §3.6) |
| Messages | `unread / read / acknowledged` | `queued / sent / delivered / opened / bounced / failed` on `EmailLog` (`:381`) — orthogonal |
| Requests | `new / in_progress / resolved` | none |

The collapse rules (i.e. "what backend statuses surface as `due` in the portal?") need to be explicit. Suggested rule for Rental: `link_sent / viewed / awaiting / failed` → portal `due`; `partially_paid / paid` → `paid`; everything else → `upcoming`. Document this in `06-availability.md`-equivalent for payments.

### 7.2 Concierge approval direction

Current spec (`product-design/03-workflows.md:436-453` §9) is **operator-driven** end-to-end: operator adds line items, operator sends payment links, guest is a passive payer. The mockup's Concierge Extras section is **guest-mediated**: every quoted line **requires guest approval** before invoicing. This is a substantive workflow change.

Two compatible models:
- **Approval is mandatory.** Every `ConciergeLineItem` enters as `quoted`, requires `:approve` before the operator can send the payment link.
- **Approval is opt-in per item.** A `requires_guest_approval` flag on the line item; the operator chooses (e.g. for tiny pre-arranged items like grocery packs that the guest has already discussed).

Recommend the second; it preserves the Quintessential flow where the guest **already** has the request in their head (they raised it via Requests) and merely needs to OK the quoted price.

### 7.3 Security deposit modelling

The mockup treats Security Deposit as a third row in the payment schedule, with a `due` date 14 days before arrival. This is **only one of the two SD paths** the spec recognises (`01-domain-model.md:331-340`):

- **Pre-auth hold** path (`pre_authed → released / captured / expired`) — typically does not look like a payable invoice; it's a card hold the guest authorises but doesn't "pay".
- **BT refundable** path (`awaiting_bt → held → refunded`) — this is a true incoming payment, and *does* look like the portal row.

The portal as shown only models the **BT-refundable** path. If a booking uses pre-auth, the row needs different copy ("We'll hold €1,420 on your card on 16 May — this is not a charge") and a different CTA ("Authorize hold" rather than "Pay Now"). The portal needs to read `SecurityDeposit.kind` and render accordingly.

### 7.4 Currency display rule violated

`product-design/02-frontend-design.md:587, 703` §6.4 is explicit: *"never render a bare number for money. The `<MoneyDisplay>` component always shows the currency code (`£12,400 GBP`, `€8,400 EUR`)."*

The mockup violates this everywhere: `BOOKING.totalAmount = "€14,200"`, every concierge amount is `€XXX` with no ISO code. The guest-facing portal needs the same rule — perhaps even *more strictly*, since payers are often in a different currency from the property. Decision needed: is the `<MoneyDisplay>` convention an operator-only rule, or does it apply to guest-facing UI too?

### 7.5 Manager identity

The mockup conflates two roles:
- **"Your Manager"** on Overview / Concierge tab (Mya Bass, +44 020 8950 — UK office).
- **"Villa Manager"** in Check-in (Kostas Papadopoulos, +30 694 — on-site Greek manager).

In the spec:
- `Booking.assigned_to` (`01-domain-model.md:202`) is an internal `User` (typically the UK ops person).
- The on-site villa manager is a `Contact` (`01-domain-model.md:286`) with role `manager` in the `ContactPropertyMapping` (`01-domain-model.md:286`).

The portal must surface both, distinctly. The data shapes already exist, but `BookingArrivalPack` (§5) needs to know which contact to pull for the on-site greeter (it might be different per booking — owner-managed vs property-managed).

### 7.6 Lead-guest authentication scope vs co-traveller scope

The Invite Guest modal copy is precise: co-travellers *"can see the property, arrival info and concierge plan, but cannot make payments or changes."* This is a **field-level** authorisation rule:

| Surface | Lead guest | Co-traveller |
|---|---|---|
| Overview tab | full | full minus Booking Guests section |
| Payments tab | full | hidden |
| Messages tab | ? | likely hidden (or read-only sub-section) |
| Requests tab | full | likely hidden (or read-only) |
| Check-in tab | full | full (same time-locks apply) |
| Concierge tab | full | full (read-only for both anyway) |

The product owner needs to decide each row. The simplest answer is: co-traveller sees `Overview (without invite section), Check-in, Concierge` only.

---

## 8. Open questions for product

1. **Auth strength.** Is email + booking reference good enough as the *only* factor, or does it gate a magic-link confirmation on unfamiliar device? (§2.2)
2. **Co-traveller scope.** What exactly does an invitee see? Explicit per-tab decision needed. (§7.6)
3. **Co-traveller cap.** Is there a max number of invitees per booking? (Implies a `Booking.adults` / `+ Booking.children` cross-check?)
4. **Messages vs EmailLog.** Are these two surfaces independent (operator can email AND post a portal message, separately) or coupled (every outbound transactional email auto-creates a portal Message)? The simpler answer is "coupled, with a flag on the message template determining whether it surfaces in the portal".
5. **Messages auth model.** Can the guest *initiate* a new thread, or only reply to threads VC starts? Mockup only shows reply, not new-thread.
6. **Request → ConciergeLineItem promotion.** When an operator accepts a request and turns it into a billable line item, does the Request stay open until paid, or close on promotion? Recommend: stays open with thread; transitions to `resolved` on item `paid`.
7. **Service category taxonomy.** Is the 12-category list (line 401) fixed for v1, or managed (operator-editable in admin)?
8. **Per-category form schema.** Hardcoded in code (§4.2 option A) or driven by a `ServiceRequestCategory.field_schema` JSON (option B)?
9. **SLA promise**. The wizard promises *"2–4 hours during business hours"*. Is this enforced (escalation, breach reporting), or just expectation-setting copy? Likely the latter for v1.
10. **Time-locked check-in fields.** Backend redaction or client gating? Recommend backend redaction with a `:reveal` endpoint that the SPA polls on the morning of arrival. (§3.5)
11. **Time-lock granularity.** Does "day of arrival" mean local midnight in `Property.timezone`, or some hours-before-`Booking.check_in_time` window?
12. **Co-traveller can see arrival pack credentials?** WiFi password yes; gate code? Recommend yes for both.
13. **Approval timeout.** What if a guest never approves a quoted extra? Auto-cancel after N days? Reminder cadence?
14. **Tier upgrade pricing.** "From approximately €500" — is that the *actual* price the operator will quote, or just a teaser? Where does the real price come from?
15. **Tier downgrade.** Mockup has no downgrade flow. Is one needed?
16. **Concierge `arranged` state.** Should the mockup's three-state arrangement enum (`confirmed / pending / arranged`) be the canonical model, or compress to two (`confirmed / pending`) with `arranged` as a `notes` tag? (§3.6)
17. **Security-deposit pre-auth vs BT.** Portal row currently shows BT-refundable shape only. Need pre-auth rendering. (§7.3)
18. **Currency policy in portal.** Does §6.4's `<MoneyDisplay>` ISO-code rule apply to the guest-facing portal? (§7.4)
19. **Manager phone in `User`.** Add `User.phone` or read it from a different field? (§3.1)
20. **`maxOccupancy` on guest portal.** This is a `Property` field, but the portal shows it as a booking-level fact. Source decision. (§3.1)
21. **Acknowledge semantics.** What does "Acknowledged" mean operationally — that the guest accepts the contents, or merely that they've read & confirmed? Display-only or load-bearing for an audit chain?
22. **VILLA_IMAGES empty.** Production needs to read `PropertyImage` rows (role-tagged `hero`, `gallery`). Decide hero-only vs gallery slideshow.
23. **Booking reference format.** Mockup uses `VC3345` (4 digits, no separator). Spec uses `BK-2391` style (`01-domain-model.md:47-48`). Pick one and align the seed format in `SystemDefaults.booking_reference_prefix`.
24. **Booking reference is the credential.** If the booking reference is part of the login factor, brute-force is a concern. Rate-limiting, lockout, and progressive friction need explicit spec.
25. **Co-traveller revoke.** Mockup has a `×` button per row but no confirm dialog. Add `<ConfirmDialog>` (cf. `product-design/02-frontend-design.md:679-697` §6.3) since access revocation is destructive.

---

## 9. Suggested reconciliation issues to file

(Continuing the numbering in `product-design/07-api-schema-reconciliation.md`.)

- **Issue 4X — Guest portal auth.** New `Guest`-scoped session model. Pick mechanism from §2.2 (A/B/C).
- **Issue 4X — `CoTravellerInvite` entity.** New domain entity + endpoints per §5/§6.
- **Issue 4X — Guest-facing Messages.** New `MessageThread`/`Message` entities, reconciled with `EmailLog`. Decide coupling per §8.4.
- **Issue 4X — `ServiceRequest` domain.** New top-level entity with threaded replies and 12-category taxonomy. JSON `payload` shape per §4.2.
- **Issue 4X — `BookingArrivalPack` entity.** Defaults inherited from a new `PropertyArrivalDefaults` 1:1 child of `Property`. Backend-redacted reveals on arrival day.
- **Issue 4X — `ConciergeLineItem` approval status.** Add `approval_status` enum (`pending / approved / declined`) orthogonal to `payment_status`. Add `arrangement_status` (`pending / confirmed / arranged`) orthogonal to both. Resolves §3.2 and §3.6.
- **Issue 4X — Security deposit display.** Render `SecurityDeposit.kind` differently in the portal (pre-auth vs BT). Resolves §7.3.
- **Issue 4X — Currency rendering in portal.** Decide whether `<MoneyDisplay>` ISO-code rule (`product-design/02-frontend-design.md:587`) applies guest-side. Resolves §7.4.
- **Issue 4X — Manager phone on `User`.** Add `User.phone` (`01-domain-model.md:303`) or alternative source. Resolves §3.1.
- **Issue 4X — Re-enable Flywire outbound `Charge` and `PaymentRequest`.** Already an open question in `workflows/11-integrations/flywire-gateway.md:36-39`; the portal makes it urgent.
- **Issue 4X — Booking-reference format.** Align mockup `VC3345` with spec `BK-XXXX` pattern (`01-domain-model.md:47-48`).

---

## Appendix A — Raw mock data inventory

For reference during backend modelling, the full set of seed constants in the mockup:

```js
BOOKING = {
  ref: "VC3345", property: "Villa Elysian", propertySlug: "villa-elysian",
  location: "Corfu, Greece", arrive: "16 May 2026", depart: "23 May 2026",
  nights: 7, adults: 10, children: 2, maxOccupancy: 10,
  checkIn: "16:30", checkOut: "10:30",
  status: "confirmed", serviceLevel: "quintessential", // "quintessential" | "signature"
  clientName: "Mr Ben Wood", manager: "Mya Bass",
  managerEmail: "mya@villacollective.com", managerPhone: "+44 (0) 208 950 1588",
  totalAmount: "€14,200", paid: "€4,260", balance: "€9,940",
  balanceDue: "30 Mar 2026", securityDeposit: "€1,420",
};

PAYMENT_SCHEDULE = [
  { desc: "Deposit (30%)",     status: "paid",     amount: "€4,260", due: "02 Dec 2025", paidDate: "02 Dec 2025", method: "Bank Transfer" },
  { desc: "Balance",           status: "due",      amount: "€9,940", due: "30 Mar 2026", paidDate: null,           method: "Bank Transfer" },
  { desc: "Security Deposit",  status: "upcoming", amount: "€1,420", due: "16 May 2026", paidDate: null,           method: "Bank Transfer" },
];

CONCIERGE_EXTRAS = [
  { service: "Airport Transfer (Arrival)",      status: "paid",     amount: "€280",   invoiceRef: "VCX-001" },
  { service: "Private Chef — Dinner Service",   status: "invoiced", amount: "€2,100", invoiceRef: "VCX-002" },
  { service: "Grocery Welcome Pack",            status: "invoiced", amount: "€320",   invoiceRef: "VCX-003" },
  { service: "Car Hire — 2× Jeep Wrangler",     status: "quoted",   amount: "€980" },
  { service: "Boat Day Trip — Ionian Explorer", status: "quoted",   amount: "€1,200" },
  { service: "Spa & Massage Therapist",         status: "quoted",   amount: "€260" },
];

CONCIERGE_SERVICES = [
  { service: "Airport Transfer",   status: "confirmed", detail: "Corfu Airport → Villa Elysian · 16 May, 15:00 · 12 pax" },
  { service: "Private Chef",       status: "confirmed", detail: "Daily dinner service · Chef Elena · 16–22 May" },
  { service: "Car Hire",           status: "pending",   detail: "2× Jeep Wrangler · 16–23 May · Hertz Corfu" },
  { service: "Boat Day Trip",      status: "arranged",  detail: "Full day · Ionian Explorer · 19 May" },
  { service: "Grocery Pack",       status: "confirmed", detail: "Pre-arrival welcome provisions · 16 May, 17:00" },
  { service: "Massage Therapist",  status: "pending",   detail: "In-villa · 2× 60 min · 20 May" },
];

CHECKIN_INFO = {
  address: "Villa Elysian, Agios Stefanos, Corfu 49081, Greece",
  directions: "From Corfu Town take the main road north towards Sidari. ...",
  accessCode: "Gate code: 4821 — Key safe code: 7734",
  wifi: "Network: VillaElysian_Guest — Password: elysian2026",
  parking: "Ample private parking available within the villa gates.",
  emergencyContact: "Kostas Papadopoulos — +30 694 123 4567 (08:00–22:00 local time)",
  nearestHospital: "Corfu General Hospital — +30 2661 360400 — 28km",
  checkIn: "16:30 on 16 May 2026",
  checkOut: "10:30 on 23 May 2026",
  notes: "Your villa manager Kostas will greet you on arrival. ...",
};

SERVICE_CATEGORIES = [
  "transfer", "chef", "car", "boat", "grocery", "spa",
  "wine", "activities", "restaurant", "shopping", "flights", "other",
];

URGENCIES   = ["low", "normal", "high", "urgent"];
CONTACT_PREFS = ["portal", "email", "phone", "whatsapp"];
```

---

*End of analysis. ~570 lines.*
