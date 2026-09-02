# GAP-098 — The legacy `ZohoId` is never sent, and the Zoho record id is never stored back

- **Severity:** 🟠 Gap (duplicate CRM records against the pre-existing
  legacy-synced estate; no round-trip identity).
- **Source:** 2026-09-01 review of Limitless' parse functions against our
  payload builders.
- **Files touched:**
  - `django_res/data_migration/loaders/integrations.py:100–120, 165` — the
    `SyncRecordZohoLoader` and its `_ZohoSpec` table list; legacy `ZohoId` →
    `SyncRecord.external_id`.
  - `django_res/integrations/models/sync_record.py:25` — `external_id`
    (indexed, unique per provider when non-empty).
  - `django_res/integrations/services/zoho_payloads.py`,
    `reservations/services/zoho_payload.py`,
    `properties/services/zoho_payload.py` — none emit `external_id`.
  - `django_res/integrations/tasks.py` — never reads or writes it.

## Problem

The legacy system had its own Zoho sync, and the dump carries `ZohoId` on
`VillaMaster`, `VillaContact`, `VillaEnquire`, `VillaQuotationMaster` and
`VillaBooking`. We already load those into `SyncRecord.external_id` — that
work is done and calibrated (including the known `VillaMaster` 88/339 shared-
ZohoId collision, `expected_gap=1`).

Nothing then uses it:

- **Not sent.** No payload builder emits `external_id`, so the Flow's only
  dedupe key is `RES_ID` — a field the pre-existing CRM records do not carry.
  Every one of them is a create rather than an update, i.e. a duplicate
  alongside the legacy-synced original.
- **Not written back.** The Flow knows the Zoho record id after its
  create/update (that is what `result.product_id` and `contact.id` hold), but
  nothing returns it to res and `push_sync_record` would ignore it if it did.
  So `external_id` stays blank for everything created since cutover, and we
  have no stable handle on a CRM record for any future read, reconcile or
  erasure confirmation.

The email-search fallback the Flows added is a symptom of this gap, not a fix
— and it is the mechanism behind the merge hazard in CHECK-001 item 1.
Sending the id we already hold removes the need for it on every legacy
record.

The blast radius depends on a fact we have not established: **how many of
those legacy `ZohoId` values still point at live records in the current CRM
org.** If the Limitless CRM is a fresh org rather than a continuation of the
legacy one, this ticket shrinks to just the write-back half. That question
should be answered before any of the fix is built.

## Proposed fix

1. **Establish the premise first.** Count non-empty `external_id` per model,
   and have Limitless confirm whether those ids resolve in the target org.
   If they don't, drop step 2 and keep step 3.
2. **Send it.** Add `external_id` (as `ZOHO_ID`) to each payload builder from
   the instance's `SyncRecord`, and have the Flows match on it when `RES_ID`
   finds nothing — *before* falling back to email, and replacing the email
   fallback for records that have one.
3. **Store it back.** Agree a response shape carrying the Zoho record id
   (the same conversation as GAP-097's error contract — one contract, not
   two), and have `push_sync_record` write it to `external_id`. Mind the
   partial unique constraint: two res rows must never claim one Zoho id, and
   the loader's shared-ZohoId precedent shows that can happen in real data.

## Acceptance

- The `external_id` premise is documented — how many rows carry one, and
  whether they resolve in the target org. (investigation, before code)
- Where a legacy `ZohoId` exists, a push updates the pre-existing CRM record
  rather than creating a second one. (verified Zoho-side)
- A create writes the returned Zoho id to `SyncRecord.external_id`. (test)
- A response claiming an `external_id` already held by a different row fails
  loudly rather than stealing it. (test)

## Dependencies

- **GAP-097** — the same response-contract conversation with Limitless;
  settle error reporting and id write-back together.
- **CHECK-001** item 1 / item 9 — the email fallback and the `searchRecords`
  lag are both consequences of having no durable external key.
- **GAP-089** — the spreadsheet historic import creates bookings that may
  correspond to legacy CRM records; worth checking whether it should carry
  `external_id` through.
