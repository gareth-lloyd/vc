# Milestones (delivery phasing)

The rest of this package is a near-complete specification of the rebuild. It does **not**,
on its own, say *what ships first*. The earlier docs use "v1" to mean "the rebuild" — a
single large deliverable. The stakeholders (scoping-session 2026-05-26; mockup-demo call
2026-05-29 with the site owner + the mockup author) were explicit that delivery must be
**milestone-driven, with scope risk minimised at each step**: *"the more we try and cram
into this scope, the more risk we put into this project… I want to do milestones."*

This file is the authoritative **phasing layer** over the design package. It does not change
any model or decision — it **re-buckets** existing, already-designed scope into Milestone 1
and Milestone 2+. Nothing here is "dropped"; the deferred items keep their full design in the
per-domain docs and `10-decisions.md`.

> **Reading order.** Treat `10-decisions.md` as *what* and *why*; treat this file as *when*.
> When a decision row and this file disagree on phasing, this file wins and the decision row
> should be updated to cite it.

## The guiding principle

**Milestone 1 = replicate the proven core + get off WordPress.** It reproduces the legacy
behaviour the business depends on every day (property data → quote → booking), hosted on the
new Django + React stack, with the guest checkout absorbed off WordPress. It deliberately does
**not** include the greenfield modules the legacy system never had (concierge depth, refund /
security-deposit lifecycle, owner portal, deeper Zoho lead-management). Those are real,
already-designed, and scheduled — just not in the first landing.

A working, data-backed M1 on a staging environment is the fastest way to de-risk the cutover
from `../ResSystem/`: it lets the team run real inquiries → quotes → bookings end-to-end on
the new platform before any further scope is committed.

## Milestone 1 — core replication + off-WordPress checkout

| Area | Scope | Specs |
|---|---|---|
| **Properties** | Catalogue, rooms, features, images, finance config. Carry over as **canonical** — the property structure originated with the prior vendor ("16i"; built for Oxford/Bramble Ski) and is now VC-owned and stable. Field-stripping per the mockup is an open follow-up (see `10-decisions.md`). | `02-properties.md`, `03-finance-config.md` |
| **Pricing** | `PricingEngine`, `RatePlan→RateCard→RateRule`, **occupancy bands** (already modeled), **next-year rate projection** + on-demand carry-forward (net-new — see risk callout). | `04-pricing.md`, `workflows/04-pricing/*` |
| **Enquiry → Quote stack** | Multi-quote per enquiry (append-only), quote-may-diverge-from-enquiry, conversion measured per enquiry, assignee + action-driven stage (already designed), **`lead_status`** (net-new field). | `05-reservations.md` (Enquiry, Quotation), `10-comms.md` (quote send) |
| **Booking** | Booking creation from an accepted quote line; booking state machine; **guest booking/checkout journey hosted in the SPA**, not WordPress (net-new — see risk callout). | `05-reservations.md` (Booking), `06-availability.md`, `workflows/09-booking/*`, `workflows/10-payment/checkout-flow.md` |
| **Availability** | Range-query availability + holds; operator calendar; **Stop Sale** in the display vocabulary (vocabulary reconciliation, small). | `06-availability.md`, `workflows/06-availability/*` |
| **Comms (minimum)** | Transactional email needed by the M1 flows (enquiry ack, quote send via agent SMTP, booking confirmation, payment/deposit emails on the checkout path). The full 23-template catalogue and template-admin UX can land incrementally. | `10-comms.md` |
| **Platform** | Staging environment backed by **fake-but-realistic seeded data** (the project's `seed_dev` seeder), so the team can exercise inquiry→quote→booking before cutover. | project `seed_dev`; `00-conventions.md` |

### Honest M1 risk callout — the two net-new surfaces

Almost everything in M1 is **replication** of proven legacy behaviour. Two items are **not** —
they are genuinely new and are therefore the real delivery risk *inside* M1. They are kept in
M1 by stakeholder direction; they are flagged here so they are tracked, not so they are cut.

1. **First-party guest checkout (off WordPress).** Removing the WordPress round-trip also
   means *building* a first-party guest checkout page **and** taking over the Flywire
   payment-return / webhook handling that is currently WordPress-proxied
   (`08-integrations.md`, `workflows/11-integrations/flywire-gateway.md`). Net security win
   (it kills the legacy unauthenticated `WordPressApi/*` checkout endpoint), but it is real new
   work, not a simplification. Scoped narrowly to the **checkout page only** — the broader
   post-booking guest portal stays deferred (`10-decisions.md` rows 68/75).
2. **Next-year rate projection.** Legacy does next-year roll-forward manually. M1 quotes a year
   with no rate plan by *lazily projecting* a guide rate from the most recent year that has
   rates (`RateProjectionService`), flagged `Quote.is_projected`, writing no rows; plus an
   on-demand `RateCarryoverService.materialise` (admin action + `:carry-forward` endpoint) to
   promote a year into editable rows when staff want to confirm/hand-tune (`04-pricing.md`). The
   risk is projection correctness — chiefly the **date-mapping rule** (same calendar date vs
   changeover-weekday alignment), an open follow-up pending Bryony's listing Loom that now gates
   the default quoting path.

## Milestone 2+ — re-bucketed from the current "v1"

Fully designed already; scheduled after M1. Each keeps its spec and decision rows intact.

| Area | Why M2+ | Specs |
|---|---|---|
| **Concierge** | Greenfield vs legacy; not on the critical quote→book path. | `workflows/09-booking/booking-concierge.md`, `07-payments.md` (`Payment.purpose=CONCIERGE`) |
| **Refund / Security-deposit / pre-auth depth** | Legacy had no refund table; the full `SecurityDeposit`/`Refund` state machines + Flywire pre-auth wiring are new. M1 can confirm bookings without the full SD lifecycle live. | `07-payments.md`, `workflows/10-payment/*` |
| **Deeper / Zoho-primary lead management** | Lead-management primacy (Res vs Zoho) is an open strategic decision (`10-decisions.md` row 93). M1 stays Res-primary, one-way push. | `08-integrations.md` |
| **Owner portal** | No legacy analog; read-only minimum is itself deferred, and owner-edit/onboarding/messaging is greenfield. Permissions layer (owners see only their own villa) is the critical prerequisite. | `product-design/02-frontend-design.md §7.3`, `10-decisions.md` row 69 |
| **Advanced finance permissioning** | M1 uses flat staff roles gating the whole finance form; per-concern permissions are a post-v1 refactor (`10-decisions.md` row 30). | `03-finance-config.md` |
| **Channel / iCal ingest** | High-value force-multiplier (~30 villas — or ~30% of the catalogue; figure unreconciled). Was post-MVP; **iCal ingest has since been built** (✅ GAP-011, `todo/done/gap-011-ical-feed-ingest.md` — engine + ops conflict alert + in-app awareness feed; awareness *digest email* deferred). Channel-manager sync proper stays out of MVP. | `06-availability.md` "Out of scope", `08-integrations.md` |
| **Full comms catalogue + template-admin UX** | The 23-template library + versioned editable admin (`10-decisions.md` rows 18, 36) lands incrementally after the M1-critical transactional emails. | `10-comms.md` |

## Out of scope entirely (v-later)

Tracked in `10-decisions.md` §Deferred — client/guest portal, group bookings, half-day
changeover, per-villa template branding, multi-language templates, multi-currency settlement,
`GuestPreference`, per-person base pricing (Kenya), etc. Not phased here; revisit when the
business need re-emerges.

## How to use this file

- Building something? Confirm which milestone it's in here **before** starting. If it's M2+
  and there's pressure to pull it forward, that's a scope-risk conversation with the owner —
  surface this file.
- Adding a new capability? Decide its milestone here and add a `10-decisions.md` row that cites
  this file for phasing.
- The two M1 risk items (checkout, next-year projection) are the ones to watch in estimation and to
  validate first on staging.
