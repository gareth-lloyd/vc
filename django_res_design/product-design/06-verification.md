# 06 — Verification & Open Questions

## How to validate this design package

Before implementation begins, walk the design through the following checks.

### 1. Walk five canonical user journeys end-to-end

For each journey, trace every screen the operator visits and every API call that would fire. Confirm both are defined in this package.

1. **New lead to confirmed booking** — A phone enquiry comes in. Operator types it. Builds a quote with three villa options. Sends with 48h hold. Guest replies picking option 2. Operator converts to booking. Sends deposit link. Webhook lands. Booking confirmed. Owner notified.
2. **Modification under pressure** — Confirmed booking, deposit paid. Guest emails three weeks before arrival asking to change dates. Operator opens booking, edits dates, sees pricing delta, decides to absorb the increase, sends notification email to guest and owner.
3. **Cancellation with refund** — Confirmed booking, balance paid. Guest cancels 30 days out. Operator opens cancel modal, policy computes 50% refund of balance, full refund of SD pre-auth release, full refund of unrendered concierge. Operator confirms; multiple refund processor calls fire; guest gets itemised email.
4. **Owner approval cycle** — Booking on a pre-approval-required villa. Deposit paid. Owner notified. Owner logs into portal, sees pending-approval card, clicks Approve. Booking advances; guest confirmation email fires; calendar transitions.
5. **Portfolio season setup** — Admin closes out 2026 by creating Summer/Mid/Low seasons across 12 properties via bulk apply with a +5% scale on the previous year's rates. Preview shows 12 properties × 3 seasons × ~6 rate cards each. Confirms; partial completion log shows 11 succeeded, 1 conflicted on a date overlap.

Each journey above should resolve to specific screens in `02-frontend-design.md`, specific steps in `03-workflows.md`, and specific endpoints in `04-rest-api-surface.md`.

### 2. Cross-check entities against the original schema

The original has ~56 tables. The new domain model (`01-domain-model.md`) covers them by:
- **Carrying over** the core booking/payment/availability/property concepts.
- **Collapsing** historical redundancy (`VillaMapping` + `VillaWebsitePricing`, `VillaContactMap` + `VillaContactMapping` + `VillaContactRoleMapping`).
- **Splitting** the embedded settings on `VillaMaster` into separate `PropertySettings` and `PropertyFinance`.
- **Renaming** to domain language (`VillaEnquire` → `Enquiry`).

For each table in the original schema, the domain doc should answer: *carried over (and renamed to what?), collapsed (into which new entity?), or dropped (with why)?* A migration script will need this mapping anyway.

### 3. Cross-check workflow side-effects against API actions

Every workflow step that mutates state names a side-effecting action. Confirm each action has a corresponding endpoint:

- `POST /bookings/{id}:confirm` — flow 6 (deposit paid → booking confirmed) and flow 15 (owner approve).
- `POST /bookings/{id}:cancel` — flow 16.
- `POST /bookings/{id}:owner-approve` / `:owner-decline` — flow 15.
- `POST /bookings/{id}:modify-dates` / `:modify-guests` — flow 5.
- `POST /quotations/{id}:send` — flow 2.
- `POST /quotations/{id}:convert` — flow 3.
- `POST /enquiries/{id}:convert` — flow 2 entry.
- `POST /bookings/{id}/deposit:request-payment` / `:mark-paid` — flow 6.
- `POST /bookings/{id}/balance:request-payment` / `:mark-paid` — flow 7.
- `POST /bookings/{id}/security/payments/{id}:hold` / `:release` / `:claim` — flow 8.
- `POST /refunds/{id}:execute` — flow 17.
- `POST /availability:bulk-block` — flow 19.

If a workflow references a side-effect with no endpoint, either the endpoint is missing or the workflow needs a different action.

### 4. Cross-check screen catalog against workflow references

Every workflow step references a screen ("Screen: Quotation Builder, full page, two-pane"). Each referenced screen should exist in `02-frontend-design.md` §3. If a workflow references a screen the frontend doc doesn't define, add it; if the frontend doc defines a screen no workflow references, ask whether it's load-bearing or aspirational.

### 5. Confirm REST API doc has no payload schemas

`04-rest-api-surface.md` is spec-only by the user's explicit constraint. Run a quick grep for telltale schema language ("returns JSON with fields:", "request body:", `{ "id":`, type names like `string`, `integer`, `uuid` outside path params) and remove any that crept in. Endpoint inventory only.

### 6. Confirm every improvement has a rationale

`05-improvements-over-original.md` lists 20 deliberate departures. Each must have a one-line **why**. Anything without a why is a candidate to walk back to match the original (familiarity is a feature; gratuitous change is a cost).

## Stakeholder review checklist

Different audiences care about different sections.

**Operations / Sales team** — primarily `02-frontend-design.md` §3 (screens), `03-workflows.md` (all 20 flows). Ask them: which flows feel wrong? Which screens lack a field they need daily?

**Owners (sample 2-3)** — primarily flow 14 (owner portal) and the relevant screens. Ask them: what would you want to do in this portal that you currently email us about?

**Engineering** — primarily `01-domain-model.md`, `04-rest-api-surface.md`, `00-overview.md` (architecture). Ask them: where's the complexity we've underestimated? What's the riskiest part of the schema?

**Finance / Accounting** — primarily flow 17 (refunds), flow 18 (reports), the money-handling rules in `01-domain-model.md`. Ask them: which reports do you actually need monthly? Which currencies have non-trivial tax rules?

## Open questions requiring user clarification before implementation

These are flagged in the design but not resolved. Each blocks at least one slice of implementation.

1. **Cancellation policy thresholds** — flow 16 references "deposit forfeit < N days from arrival, 50% / 25% / 0% sliding scale on balance". The original system had policies per villa; should the new system store them as named policy templates (Strict / Moderate / Flexible) selectable per villa, or per-villa custom values? (Recommendation: named templates with per-villa override.)

2. **Owner pre-approval SLA** — flow 15 references "if owner doesn't respond within site-configured window, escalation / optional auto-approval". Confirm the default window (24h? 48h? 72h?) and whether auto-approval-on-timeout is acceptable to the business.

3. **Channel sync scope** — `04-rest-api-surface.md` §2.25 lists Airbnb / Booking.com / VRBO. Confirm which channels are in scope for v1 vs v2. (Each channel is meaningful engineering effort.)

4. **Hold expiry default** — flow 10 uses 48h as the default. Confirm and whether per-site override is needed.

5. **Currency display normalisation in reports** — `02-frontend-design.md` §3.15 mentions "normalise to a chosen base currency for charts". Confirm the base (GBP? EUR? per-site?) and FX source (real-time? daily snapshot?).

6. **Owner statement scheduling** — flow 18 references "Run this monthly". Confirm cadence (monthly / quarterly / on-demand) and delivery channel (email PDF attachment / portal-only / both).

7. **Concierge supplier directory** — the design treats suppliers as contacts (flow 9). Confirm this matches the operating model, or whether suppliers need their own entity with contracts, payment terms, etc.

8. **2FA enforcement** — design says "admin-forced for users with `is_admin` and any operator who touches refunds". Confirm.

9. **Multi-site inventory sharing** — `VillaBooking` originally had a `Booked-VC` status indicating a booking from another VC site. The design carries this over. Confirm sites do share inventory (one villa visible on multiple branded sites), or whether each villa is exclusive to one site.

10. **Guest data retention / GDPR** — `04-rest-api-surface.md` §2.17 lists `POST /guests/{id}:anonymize`. Confirm retention policy (default keep-forever, anonymise on request? Or auto-anonymise N years after last booking?).

11. **Email templates inheritance** — design assumes templates can be per-site (white-labelled). Confirm; clarify the inheritance chain (system default → site override → property override?).

## Resolved questions

- **Payment gateway** → **Flywire** (continuing the legacy integration; no Stripe / multi-provider in v1). See `10-decisions.md` and `workflows/11-integrations/flywire-gateway.md`.

13. **Rate card "incomplete pricing"** — flow 2 step 4 references "if villa's rate card incomplete for some nights, card flags 'Incomplete pricing — manual quote'". Confirm whether this is acceptable (operator types a price) or whether incomplete pricing should hide the villa entirely from results.

14. **Audit log retention** — confirm retention window (forever / 7 years / per regulatory requirement) and whether the operator UI should expose it or it's admin-only.

15. **Owner financial visibility** — flow 14 references `view_full_money` and `view_guest_details` permissions per owner-property mapping. Confirm the default for new mappings.

Decisions on these answers will be folded back into the relevant docs before code starts.

## What "done" looks like for this design package

This package is ready for implementation when:

- [ ] All five canonical journeys (above) trace cleanly through screens + workflows + endpoints with no gaps.
- [ ] Every original schema table has a known fate (carry / collapse / drop) in `01-domain-model.md`.
- [ ] No payload schemas in `04-rest-api-surface.md`.
- [ ] Every improvement in `05-improvements-over-original.md` has a why.
- [ ] All open questions above have answers, or are explicitly deferred to a v2 with a written note.
- [ ] Operations, Owners (sample), Engineering, and Finance stakeholders have signed off on the sections relevant to them.

Until then the design is a draft and implementation work should not begin in earnest (small spikes for unknowns are fine; full vertical-slice features are not).
