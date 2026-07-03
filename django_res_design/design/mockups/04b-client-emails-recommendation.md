# Client Emails — Recommendation

> Companion to `04-client-emails.md` (mockup analysis) and `04a-ressystem-email-inventory.md` (legacy inventory).
> Cross-references: `../10-decisions.md`, `../10-comms.md`, `../workflows/12-automation/`.

## 1. TL;DR

- The mockup at `https://vc-emails.netlify.app/` is a strong **visual style guide** for transactional comms — accent palette, footer lockup, two-rail payment CTAs, danger-banner pattern — but it is **not** the v1 spec for the email catalogue.
- The catalogue itself should be **rebuilt from the workflow side**, not from the mockup. The workflow files (`workflows/07-enquiry/`, `workflows/08-quotation/`, `workflows/09-booking/`, `workflows/10-payment/`, `workflows/12-automation/`) demand roughly **twice the templates** the mockup ships, including the operator- and owner-facing ones the mockup omits entirely.
- The mockup's lifecycle additions (distinct 3-day balance reminder, paid-in-full variant, balance-received, pre-arrival 7d, check-in 48h, post-stay thank-you) are **good improvements over legacy** and belong in v1.
- The mockup's portal-dependent templates (`New Message from VC`, `Service Request Update`, `Owner Approval Request with self-service tokens`, `Upgrade Service Level`) **follow the portal deprioritisation in `../10-decisions.md`** and slip to a later phase. The notification path that operators care about (legacy `OWNER_BOOKING_CONFIRM` semantics) stays.
- Infrastructure work — `EmailLog`, editable `EmailTemplate` admin with versioning + preview + test-send, per-booking Communications tab, dropped BCC, encrypted SMTP creds, Celery beat scheduler — is **independent of the mockup** and lands first.

## 2. What to take from the mockup (in scope for v1)

These are the items the mockup gets right that aren't in the legacy: keep them and wire them to existing workflow triggers.

| Template | Rationale | Mockup ref | Workflow trigger |
|---|---|---|---|
| **Cadence refinement: 7d / 3d / due-today as three keys** | Legacy reuses `BALANCE_PAYMENT` for both the 7-day and day-of nudges (`04a` §6 #1, `04-client-emails.md` §3.7). Three distinct `EmailTemplate.key` rows let each carry its own urgency (tan / gold / red), subject prefix, and copy. | `04-client-emails.md` §3.5 / §3.6 / §3.7 | `workflows/12-automation/scheduler-jobs.md` `send_payment_reminders` (live per `../10-decisions.md`), `workflows/09-booking/payment-schedule.md` |
| **Booking Confirmation (Paid in Full) variant** | Legacy `BOOKING_RECEIPT` is reused whether or not the balance is satisfied (`04a` §9 row #2). A separate template avoids identical subject lines and the "are you sure you've paid the rest?" support ticket. Implement as a render branch on the same key, **not** a parallel template — subject differentiation goes via context, copy via `{% if booking.is_paid_in_full %}`. | `04-client-emails.md` §3.2 | `workflows/10-payment/payment-collection.md` (on guaranteed-payment webhook where `paid_total == total_amount`) |
| **Balance Payment Received notification** | Legacy has no "money's in" confirmation distinct from `BOOKING_RECEIPT` — the same template re-fires (`04a` §9 row #4). The mockup's green-accent variant makes the lifecycle state legible. | `04-client-emails.md` §3.4 | `workflows/10-payment/payment-collection.md` `PAYMENT.COLLECTION.WEBHOOK_RECEIVE` step 6 |
| **Pre-Arrival Information (`arrive − 7d`)** | Legacy has nothing in this slot. The Balance-Received body already promises "Our experience team will be in touch shortly with your pre-arrival information" (`workflows/10-payment/payment-collection.md:94`), so the absence is a visible debt. | `04-client-emails.md` §3.11 | New scheduler tier in `workflows/12-automation/scheduler-jobs.md` (see §5 below) |
| **Check-In Reminder (`arrive − 48h`)** | Legacy has nothing. Useful for last-mile logistics (parking, transport handoff, arrival window). | `04-client-emails.md` §3.12 | Same scheduler tier — second cadence row |
| **Post-Stay Thank You (`checked_out + 24h`)** | Legacy has nothing. Even without a review-collection workflow, a thank-you note costs nothing and supports brand. | `04-client-emails.md` §3.13 | New `Booking.checked_out_at` timestamp + scheduler tier |
| **Visual style guide** (accent palette, footer lockup, two-rail payment CTAs, danger banner) | Net upgrade on legacy. Should ship as a **shared base template** with per-message accent + alert-box partials, not duplicated per template. | `04-client-emails.md` §6 | `comms` app templates directory (`../10-comms.md`) |

## 3. What to defer (portal-dependent)

These follow the deprioritisation in `../10-decisions.md` Deferred table — guest portal and owner-self-service are out of v1, so the mockup templates that depend on those primitives go with them.

| Template | Reason for deferral | Which deprioritisation it sits under |
|---|---|---|
| **New Message from VC** | Needs a `BookingMessage` / `Thread` entity, an inbound-email gateway (per-booking reply-to aliases), and a guest-portal "view conversation" surface. None of these exist; all are part of the guest-portal track. | `../10-decisions.md` Deferred row "Client / guest portal" |
| **Service Request Update** | Needs a richer `ConciergeLineItem` state machine (supplier-confirmed / dispatched / cancelled) on top of the existing payment-state axis, plus the guest-portal ticketing surface. | `../10-decisions.md` Deferred row "Client / guest portal" — specifically the "concierge ticketing" sub-bullet |
| **Owner Approval Request with self-service approve/decline tokens** | The **notification email itself stays** (see §4), but the actionable Approve/Decline URLs that point at owner-portal self-service screens go. v1 reverts to the legacy "owner replies by email, ops transcribes the answer" pattern documented in `workflows/09-booking/booking-confirmation.md:47`. | `../10-decisions.md` Deferred row "Owner portal beyond read-only view" |
| **Upgrade Service Level confirmation** (any "self-served from the portal" path) | Guest-driven upsell needs the guest portal. The operator-driven equivalent (`UPGRADE_CONCIERGE_SERVICE_REQUEST` in legacy — `04a` §5 row #3) stays as an internal-ops template. | `../10-decisions.md` Deferred row "Client / guest portal" |

## 4. What to add that the mockup is missing

Grouped by the workflow that already demands the email. The mockup catalogues 14 templates; the workflow side demands at least 20+ once the operator- and owner-facing surface is included.

### Enquiry workflow (`../workflows/07-enquiry/`)

| Template | Workflow ref | Legacy ref | What it contains |
|---|---|---|---|
| **Enquiry auto-reply to guest** | `workflows/07-enquiry/enquiry-intake.md` | `VC_ENQUIRE_AUTO_REPLY` | Acknowledges receipt of a public-site enquiry; sets agent SLA expectation; carries agent signature when an enquiry is auto-routed. |
| **Internal enquiry notification to VC inbox** | `workflows/07-enquiry/enquiry-intake.md` | `VC_ENQUIRE_EMAIL` | Pushes enquiry summary into the ops inbox. Even with Slack/Teams in play, an email-of-record is still needed for forwarding and CC'ing third parties. |

### Quotation workflow (`../workflows/08-quotation/transmission.md`)

| Template | Workflow ref | Legacy ref | What it contains |
|---|---|---|---|
| **Quotation email to client** | `workflows/08-quotation/transmission.md` | Hardcoded subject `"Quotation from Villa Collective"` in legacy `SentQuotation` | Renders the quotation as an inline HTML email — no PDF attachment (legacy is HTML-only; the quote PDF was dropped, see decision #19 reversed). **Per-agent "send as" via per-user SMTP** — this is a live decision in `../10-decisions.md` ("Per-user SMTP reinstated as `comms.SmtpProfile`"). Note `04a` §10 finding #9: the legacy plumbing exists in `UserMaster` but is dead-coded (`SentQuotation` not wired to any active page). Django port re-activates it on this template only. |
| **Quotation reminder to guest** (optional, debounced) | `workflows/08-quotation/lifecycle.md` | None | Soft chase if `Quotation.status` stays `sent` past N days. v1.1 candidate; ship the template, gate the scheduler. |

### Booking workflow (`../workflows/09-booking/`)

| Template | Workflow ref | Legacy ref | What it contains |
|---|---|---|---|
| **Owner approval notification** (plain) | `workflows/09-booking/booking-confirmation.md` | `OWNER_BOOKING_CONFIRM` (commented-out direct send, replaced by `sp_owner_template` fan-out) | Notifies the owner that a booking is awaiting confirmation. **No self-service tokens** in v1 — owner replies by email, ops transcribes. Same template carries net figures (`netTotal`, `netDeposit`, `netBalance`, `commissionRate`). |
| **Owner declined → guest notification** | `workflows/09-booking/booking-confirmation.md` (decline path) | None | Apology + offer to rebook elsewhere. Fires when ops marks `Booking.owner_approval = declined`. |
| **Booking modification notice (guest)** | `workflows/09-booking/booking-modification.md` | None — legacy modifies in place silently | Debounced preview-then-send when a confirmed booking is changed (party size, dates, services). The `cancel-and-rebook` decision in `../10-decisions.md` means most post-deposit changes go via the cancellation + new-booking path; in-place changes still need a notice. |
| **Booking modification notice (owner)** | `workflows/09-booking/booking-modification.md` | None | Owner counterpart, debounced (no spam on burst edits). |
| **Cancellation confirmation (guest)** | `workflows/09-booking/booking-cancellation.md` | None — legacy had no cancellation workflow | Itemised refund summary. Builds on the live `RefundService.from_cancellation` decision in `../10-decisions.md`. |
| **Cancellation notification (owner)** | `workflows/09-booking/booking-cancellation.md` | None | Owner counterpart. |
| **Refund confirmation (guest)** | `workflows/10-payment/payment-collection.md` (refund path) | None | Fires when the gateway acknowledges a `Refund` row has been processed. Distinct from cancellation confirmation because partial refunds can happen outside cancellation (damages, goodwill). |
| **Damages-claim email (guest)** | `workflows/09-booking/booking-cancellation.md`, `../10-decisions.md` open follow-up "`DamageClaim` model" | None | Itemised deduction notice tied to the deferred `DamageClaim` model. Ship the template scaffold even if the model lands later — guard with `{% if booking.damage_claim %}`. |

### Payment workflow (`../workflows/10-payment/`)

| Template | Workflow ref | Legacy ref | What it contains |
|---|---|---|---|
| **Security deposit request** (distinct) | `workflows/10-payment/payment-collection.md`, `workflows/12-automation/scheduler-jobs.md` | `SECURITY_DEPOSIT_PAYMENT` | The mockup folds SD into the body of `Booking Confirmation`. Legacy has it as its own template; the redesign should too — SD lives on its own state machine (`SecurityDeposit` is a first-class workflow model per `../10-decisions.md`) and its own cadence (~14d before arrival, see `04` §3.1 note about the 14-day vs legacy 7-day discrepancy). |
| **Deposit due / "Proceed to Booking" chase** | `workflows/12-automation/scheduler-jobs.md` | `INITIAL_PAYMENT_TEMPLATE` | The initial deposit request *is* the mockup's "Proceed to Booking" template. If a guest doesn't pay within the hold window, the chase fires. Legacy has this; mockup does not. |
| **Stored-card refresh request** | `workflows/12-automation/scheduler-jobs.md` | `CC_CARD_UPDATE` | Niche but real — fires when a card-on-file balance is due and the token has expired / been replaced. Required to keep auto-charge tracks live. |
| **Concierge upsell to ops** | `workflows/10-payment/checkout-flow.md` | `UPGRADE_CONCIERGE_SERVICE_REQUEST` | Internal-ops notification when a guest ticks the "I want concierge" box at checkout. Different from the guest-facing concierge invoice (mockup §3.8). |

### Automation (`../workflows/12-automation/scheduler-jobs.md`)

| Template | Workflow ref | Legacy ref | What it contains |
|---|---|---|---|
| **Scheduled-report delivery** | `workflows/12-automation/scheduler-jobs.md` (and `product-design/03-workflows.md` flow 18) | None | Recurring reports emailed to a recipient list with attachment. Operator-configurable cadence. |
| **Overdue-ops escalation** | `workflows/12-automation/scheduler-jobs.md`, `workflows/09-booking/payment-schedule.md` | None | When a booking transitions to `Overdue` and the configured grace window expires, the escalation email fires to a configured ops address. |
| **Hold-expiry notification to creating agent** | `workflows/12-automation/scheduler-jobs.md` (open question `:91`), `../10-decisions.md` live row "Hold auto-expiry enabled from day one" | None | Tells the agent who placed the hold that the system released it. Already live as a decision; just needs a template body. |
| **Manual invoice request to accounts** | `workflows/09-booking/booking-management.md` | Hard-coded HTML in `SentInvoiceMailByBookingId` (`04a` §3.3) | Internal-ops email asking accounts to issue a manual invoice. Move off hard-coded HTML into a real `EmailTemplate`. |

## 5. Infrastructure we need regardless of the mockup

Each of these is load-bearing for the catalogue and independent of which templates are in v1.

- **`EmailLog` table.** Already live in `../10-decisions.md` (the `comms` app row). **Confirm and ship.** Replaces the legacy per-day plaintext ResLogs files (`04a` §2.4). Persist-first, append-only; carries rendered subject/body, recipient(s), provider message-id, status, opened/clicked timestamps. Forensic, not a messaging primitive.
- **Per-booking Communications tab.** Net-new operator UX with no legacy analog. Should be added to `product-design/02-frontend-design.md §3.8` Booking Detail tabs (alongside Overview / Payments / Concierge / Activity). Lists every `EmailLog` row tied to the booking with status chips, expand-to-render-preview, resend button. Closes the "operators cannot see what fired" gap from `04a` §10.
- **Editable email-template admin with versioning, preview-with-data, test-send.** Today `VCEmailTemplates` is SQL-only (`04a` §3.1, §8 row 1) — operators edit copy by raw SQL or by raising a dev ticket. This is the **biggest operator-pain point** in the legacy and the single highest-ROI piece of catalogue tooling. v1: list / edit / version-history / preview-against-booking-id / test-send-to-me. `product-design/04-rest-api-surface.md:667-677` already scopes most of this — promote `preview` and `test-send` from v1.1 to v1.
- **Per-agent send-as via per-user SMTP** (`comms.SmtpProfile`, scope=PERSONAL, encrypted creds). Already live in `../10-decisions.md`. **Reaffirm and wire to the quotation template only.** Note from `04a` §10 finding #9: the legacy plumbing is dead-coded (`SentQuotation` not wired to any active staff page), so the rebuild is the reactivation of an existing capability, not a new feature.
- **Drop the hardcoded BCC** `connectusinfowaydemo12@gmail.com` (`04a` §2.3 — leaks every non-quote email to a dev-vendor Gmail). Flag in security checklist. Do not port.
- **Replace cleartext SMTP password storage** (`VillaConfigEmail.serverpassword` and `UserMaster.SmtpPassword` are both plaintext in legacy — `04a` §2.1, §2.2). Encrypt-at-rest with fernet/KMS-backed key; redact in admin display.
- **Replace external HTTP-cron with proper scheduler** (Celery beat). Already live in `../10-decisions.md` ("All Celery beat tasks enabled in v1"). **Reaffirm.** Closes the legacy pattern of a static-GUID-authed `GET /api/WordPressApi/Payment/BookingEmailReminder` endpoint hit by external cron (`04a` §6 row #1).
- **Email-failure surface in operator admin.** Today the only signal beyond a UI toast is a plaintext file in `wwwroot/ResLogs/` (`04a` §8). Build a "Failed sends" tab (last 24h / 7d, by template, with retry). Cheap once `EmailLog` exists.
- **Suppression list / bounce handling.** `EmailLog.status` already covers `bounced`; add a `SuppressedAddress` table for hard-bounces and complaints so we don't keep retrying a dead address.
- **Provider webhook ingestion** (open / click / bounce) — modelled on the existing Flywire webhook pattern (`workflows/10-payment/payment-collection.md`). Adds an `EmailEvent` row per provider callback so the Communications tab can show real delivery state.
- **Inbound-email gateway** — **out of v1**. Lives with the guest-portal deferral. Mention here only so we don't pretend `New Message from VC` is "almost-ready"; it isn't.

## 6. Open questions

1. **Booking Confirmation: deposit-paid vs paid-in-full — separate templates or single key with a render branch?** Recommend single key with a conditional. Subject differentiation goes via context (e.g. `{% if paid_in_full %}Paid in Full — {% endif %}Booking Confirmed — …`) so Gmail threading doesn't collapse them.
2. **Reminder cadence granularity — system-fixed or per-booking overridable?** `product-design/03-workflows.md` flow 7 hints at "per site (e.g., 60 days before, 45, 30, 14, 7, 3, 1, day-of, overdue +3, +7)". Recommend **per-site default in `SystemDefaults`, per-booking override on `Booking.payment_reminder_overrides` JSON** for the long tail of "this VIP gets a softer cadence" cases.
3. **Owner emails: actionable vs plain.** With the owner portal deferred, the v1 owner emails are notifications only — no Approve/Decline links. Confirm that's acceptable to the business or revisit owner-portal priority.
4. **Operator-internal emails — same template system or separate?** Recommend **same**, scoped by `EmailTemplate.audience ∈ {guest, owner, internal, supplier}`. Single admin surface, single send pipeline; the audience field gates which merge fields are exposed in preview.
5. **`Booking.checked_out_at` source of truth.** Required for the Post-Stay template. Auto-set by the `auto_check_out` Celery task at `arrive_date + nights` (already live per `../10-decisions.md`)? Or operator-confirmed via a "mark checked out" action? Defaulting to the scheduler value is simpler; expose an override field for late-departures.
6. **`holdExpiresIn` value** — the mockup body says **"5 working days"**, `product-design/03-workflows.md:106` says **48h**, legacy `AvailableStatus=40` uses **7 days**. Three numbers in three places. Pick one (recommend 48h post-quote-conversion) and codify in `SystemDefaults`.
7. **Review-collection on Post-Stay** — purely thank-you, or does it carry a Trustpilot / Google / internal review link? Out of v1 either way; flag for v2.
8. **Subject differentiation across the catalogue.** Mockup §3.1 and §3.2 currently share a byte-identical subject. Same risk on 7d / 3d / today reminders if rendered carelessly. Add a subject-uniqueness check to the template-admin save path.

## 7. Suggested sequencing

### Phase 1 — Foundational (ship first, unblocks everything)

- `comms` app skeleton (`EmailTemplate`, `EmailLog`, `EmailService.send(...)`) — already specced in `../10-comms.md`.
- Editable `EmailTemplate` admin with **versioning, preview-with-data, test-send**.
- Per-booking **Communications tab** in operator UI.
- Drop hardcoded BCC; encrypt SMTP creds; remove cleartext storage.
- Celery beat scheduler standing in for the external HTTP-cron.
- Port the **legacy 5 templates that already work**: `INITIAL_PAYMENT_TEMPLATE` ("Proceed to Booking"), `BOOKING_RECEIPT` ("Booking Confirmation"), `BALANCE_PAYMENT` reused as the 7d nudge, `CONCIERGE_PAYMENT_TEMPLATE`, owner notification (legacy `OWNER_BOOKING_CONFIRM` semantics via `SentEmailToOwner`).

**Definition of done:** every legacy email path is replaced like-for-like, with an `EmailLog` row per send and an admin surface to edit copy without raising a dev ticket.

### Phase 2 — Catalogue completion (close the workflow debts)

- Enquiry auto-reply + internal enquiry notification (`workflows/07-enquiry/`).
- Quotation send with per-user SMTP (`workflows/08-quotation/transmission.md`, `comms.SmtpProfile`).
- Owner-declined → guest notification, booking modification notice (guest + owner), cancellation confirmation (guest + owner), refund confirmation (`workflows/09-booking/`).
- Security-deposit request as a distinct template; deposit-due chase; stored-card refresh (`workflows/10-payment/`, `workflows/12-automation/`).
- Scheduled-report delivery, overdue-ops escalation, hold-expiry notification, manual-invoice request (`workflows/12-automation/`, `workflows/09-booking/booking-management.md`).

**Definition of done:** every email the workflows demand has a `EmailTemplate.key`. No more hard-coded HTML in services (kills `SentInvoiceMailByBookingId`).

### Phase 3 — Lifecycle additions (mockup novelties)

- Pre-arrival (`arrive − 7d`), check-in reminder (`arrive − 48h`), post-stay thank-you (`checked_out + 24h`).
- Distinct 3-day balance reminder + danger-styled due-today.
- Paid-in-full render branch on `BOOKING_RECEIPT`.
- Balance Payment Received as its own template (green accent).

**Definition of done:** new `BookingScheduledMessage` table backs all the precomputed cadence rows. Operators can preview and adjust the schedule per booking. Mockup-style accent palette is wired through the base template.

### Phase 4 — Deferred (return when portals come back)

- New Message from VC (needs `BookingMessage` + inbound-email gateway).
- Service Request Update (needs richer `ConciergeLineItem` state machine).
- Owner approval with self-service approve/decline tokens (needs owner-portal session model).
- Any guest-portal-initiated upsell confirmation.

**Definition of done:** revisited at the point the guest/owner portal lands; not before.
