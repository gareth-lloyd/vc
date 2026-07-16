# GAP-081 — Outbound push: res → Zoho Flow webhooks (contacts, enquiries, quotes, bookings)

- **Severity:** Gap
- **Source:** 2026-07-15 Villa Collective / Limitless meeting (Zoho integration
  call — Gareth, Nick, Alice, Ben, Jake). This is the "external spec" the
  2026-07-08 INDEX note said Zoho was blocked on.
- **Files:**
  `design/backend/08-integrations.md` (superseded Zoho half — see below),
  `legacy/workflows/11-integrations/zoho-crm.md` (payload field reference),
  `legacy/workflows/07-enquiry/enquiry-intake.md` (`ENQUIRY.INTAKE.ZOHO_PUSH`
  trigger point), `django_res/integrations/` (models exist, no push machinery)

## Problem

The new system has no outbound push to Zoho at all, and the design it would
have been built against no longer matches what was agreed with the CRM vendor.

The 2026-07-15 call settled the integration contract, and it is materially
simpler than the frozen `08-integrations.md` design (OAuth `ZohoSyncClient`
against the Zoho CRM API, bidirectional pull, nightly fingerprint
reconciliation):

- **Transport: Zoho Flow webhooks.** Limitless provisions one webhook URL per
  object type; res POSTs JSON to it. Flow (their side) does all CRM mapping,
  error logging, and alerting. **No OAuth on the res side** — the endpoint URL
  set is the credential surface.
- **Upsert semantics.** One endpoint per object type; no create/update split,
  no delete endpoint (deferred until a need appears). Re-sending a record must
  be safe.
- **Send every field.** Flow ignores what it doesn't need; their mapping is
  built from *received* data, not a written spec, so adding fields later is
  free. Holding fields back is the only expensive mistake.
- **Res primary IDs are the dedupe keys.** Every payload carries the res PK
  for its object (and the PKs of nested objects — e.g. a quote payload embeds
  contact + villa identifiers). Flow routes upsert-vs-insert on those keys.
  Duplicate *prevention* logic stays in res; Zoho only maps.
- **One-way push, Res-primary.** Zoho is a passive data store for marketing
  segmentation, reporting, and email-thread history. Res keeps pricing, quote
  calculation, and transactional email. Sales staff read enquiries and send
  ad-hoc mail from Zoho but click through to res to create quotes/bookings.
  No pull, no reconciliation loop.
- **Environment pairing.** Sandbox res posts to the Zoho *sandbox* Flow
  endpoints (a permanent test path, agreed on the call). At go-live Limitless
  deploys the sandbox CRM config into live, **clears the old live CRM data**,
  and issues a second endpoint set for live res. Endpoint URLs must therefore
  be per-environment config, never code.
- **Object types**, in delivery order agreed on the call: **contact** (first,
  simplest), **enquiry** (first real traffic — WordPress-intake enquiries),
  **quote**, **booking** (endpoint provisioned but dormant until the booking
  build, ~Sept).

Two knock-on consequences worth stating explicitly:

1. **The Zoho half of "Migrating legacy external IDs" is likely mooted.**
   `08-integrations.md` and `legacy/workflows/11-integrations/zoho-crm.md`
   treat legacy `ZohoId` continuity as the critical cutover gate — but that
   assumed pushing updates into the *existing* CRM records. The meeting agreed
   the live CRM is wiped at go-live and re-seeded from (a) new res pushes
   keyed on res PKs and (b) Nick's cleaned historical spreadsheets imported
   Zoho-side. Confirm before deleting anything, but the `SyncRecordZohoLoader`
   duplicate-avalanche scenario no longer applies. The WordPress half of that
   section is untouched.
2. **A bulk backfill through the same endpoint is the planned historic-data
   path** (Gareth's suggestion, accepted on the call): once the legacy →
   Postgres load runs, replay the loaded records through the push pipeline so
   Zoho gets seeded exactly the way live traffic will flow. Zoho task-billing
   headroom was checked on the call (9,000 free Flow tasks/month vs ~4k
   enquiries + ~700 bookings *total*): a one-off bulk replay is affordable;
   steady-state volume is nowhere near the cap.

## Proposed fix

Build in `django_res/integrations/` as a thin webhook pusher, not the designed
`ZohoSyncClient`. Keep `SyncRecord` as the per-object push-state row
(`provider=ZOHO_CRM`, `external_id` = Zoho record id if Flow ever returns one,
else blank; `last_pushed_at`, `status`, `error_message`) so ops can answer
"what failed to push?" — but drop `OAuthCredential`, pull, fingerprints, and
the nightly reconcile for Zoho.

### Unit 1 — push plumbing + contact endpoint

- Settings: `ZOHO_FLOW_WEBHOOKS = {"contact": url, "enquiry": url, ...}` from
  env, per environment (sandbox res → sandbox Flow, live → live). Missing URL
  = push disabled for that type (dev default), not an error.
- Serializer per object type that dumps **everything** — model fields plus the
  res PK under an unambiguous key (legacy precedent: `RES_ID`), nested contact
  / villa sub-objects with their own PKs. Full-fat by policy; leaving fields
  out is the failure mode, not including them.
- Delivery: domain signal → receiver enqueues a Celery task (follow the
  comms pull-only receiver pattern, GAP-058) → task POSTs JSON, updates the
  `SyncRecord`. Retry with backoff on transport errors — the legacy
  fire-and-forget/no-retry posture is a named departure
  (`design/departures.md` flags it); Flow alerts on their side, the
  `SyncRecord` row is ours.
- First object: **contact** (Limitless delivers this endpoint first).

### Unit 2 — enquiry push

Fire on enquiry create/update (the `ENQUIRY.INTAKE.ZOHO_PUSH` slot in the
legacy workflow). WordPress-intake enquiries (`POST /api/wordpress/enquiries/`,
still inbound per `08-integrations.md`) are the first real traffic. Include
`Enquiry.lead_status` and lost-reason — the CRM tags the design already
promised (`design/decisions.md`, `05-reservations.md`).

### Unit 3 — quote push

Fire on quotation send (legacy trigger: `QUOTATION.TRANSMISSION.SEND_EMAIL`).
Payload embeds requirement fields, per-villa line items, and money fields —
use the legacy `QuotationPostData` field list
(`legacy/workflows/11-integrations/zoho-crm.md`) as the completeness
checklist, mapped to current models.

### Unit 4 — booking push (dormant)

Same shape, fires on booking lifecycle events. Endpoint will exist Zoho-side
before the res booking build lands (~Sept); ship the serializer + task
whenever bookings do, nothing blocks on it.

### Unit 5 — historic backfill replay

Management command: iterate loaded legacy records, feed them through the same
push tasks (rate-limited). Run once against the sandbox as the integration
test, again at go-live against live. Not a `data_migration` loader — it
replays *through* the production pipeline deliberately.

Timeline context from the call: Limitless delivers endpoints over ~2 weeks
(contact first), joint testing end-July/early-Aug, go-live first-half-to-mid
August. Progress check-in booked for Mon 2026-07-27.

## Acceptance

- Each object type POSTs full-field JSON (res PKs on the record and all nested
  objects) to its configured Flow URL on the agreed lifecycle events.
- Re-sending the same record is safe end-to-end (upsert observed Zoho-side).
- Endpoint URLs are per-environment settings; sandbox res never posts to live
  Flow and vice versa; unset URL = silently disabled (dev).
- Transport failure → retry with backoff; terminal failure visible on the
  `SyncRecord` row (status + error), no silent drops.
- No delete calls; no OAuth code paths for Zoho; transactional email
  completely untouched.
- Backfill command replays legacy-loaded records through the identical
  pipeline, idempotently.

## Dependencies

- [GAP-028](gap-028-admin-integrations-surface.md) — the admin
  `/system/integrations` read surface over `SyncRecord`/`SyncRun` rows this
  work produces; its `OAuthCredential` CRUD half is likely mooted for Zoho
  (note added there).
- [GAP-002 ✅](done/gap-002-integrations-empty-url-surface.md) /
  [Q-003 ✅](done/q-003-channel-sync-scope.md) — the old "Zoho webhook,
  slice 2" lineage; that was a different (inbound/channel-sync) scope and was
  deferred, not built. This ticket is the outbound push.
- `design/backend/08-integrations.md` — **supersedes** its OAuth
  `ZohoSyncClient` / bidirectional / reconciliation design for Zoho
  (departure note added there); `SyncRecord` and the inbound WordPress
  enquiry endpoint remain valid.
- `design/decisions.md` "Lead-management primacy: Res vs Zoho" — settled
  Res-primary one-way push by the 2026-07-15 call (row annotated).
- `design/milestones.md` M2+ "Deeper / Zoho-primary lead management" —
  unchanged; this ticket is the M1 Res-primary push it presupposes.
- WordPress enquiry intake (inbound WP → res) is a hard prerequisite for
  Unit 2's real traffic but a separate concern — do not conflate the
  directions.
- `design/departures.md` — `VILLLA_MASTER` module typo is preserve-for-compat
  if Flow's mapping ever references legacy module names; with a wiped CRM at
  go-live, Limitless may fix it Zoho-side — ask before cargo-culting the typo.
