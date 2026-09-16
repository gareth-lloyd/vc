# GAP-097 — Zoho push response contract: a push is marked `IN_SYNC` on any HTTP 2xx, and no CRM record id ever comes back

> **Scope widened 2026-09-16 (todo consolidation):** absorbs **GAP-098**
> (legacy `ZohoId` never sent, Zoho record id never stored back) — see
> §"Merged from GAP-098" at the end. Both halves need the same change to
> what the Limitless Flows return (a machine-readable result carrying the
> CRM record id or the rejection), so they are one conversation and one
> ticket. The premise check from GAP-098 (do the legacy ids still resolve in
> the target org?) still comes first for the id half.

- **Severity:** 🟠 Gap (silent divergence — res reports success for pushes
  the CRM rejected; undermines every other Zoho ticket's verification).
- **Source:** 2026-09-01 review of the three Limitless Flow functions
  (`limitless_parse_res_contact`, `limitless_parse_enquiry`,
  `limitless_upsert_villa`) against our delivery task.
- **Files touched:**
  - `django_res/integrations/tasks.py:102–125` — `httpx.post`, then
    `response.is_success` → `IN_SYNC` + `last_pushed_at`.
  - `django_res/integrations/models/sync_record.py` — `SyncStatus`,
    `last_error`.

## Problem

`push_sync_record` treats any 2xx as success and stamps the `SyncRecord`
`IN_SYNC`. What a 2xx actually means today is "the Flow received the webhook
and its Deluge function ran to completion" — nothing about whether the CRM
write succeeded. None of the three parse functions inspects the response of
its own `createRecord`/`updateRecord`/`add_tags` call, so a rejected write
returns 200 to us and we record it as delivered.

Every failure mode found in the 2026-09-01 review lands in that blind spot:

- a mandatory `Last_Name` rejection on an agency-only contact (CHECK-001
  item 2);
- an unrecognised picklist `actual_value` — `RES_Status`, `Enquiry_Source`,
  `Floor` (CHECK-001 item 8, CHECK-003 item 5);
- a Zoho duplicate rule refusing the record;
- a subform payload Zoho declines (CHECK-003 item 3).

The practical consequence is that the `SyncRecord` table cannot be used to
answer "is the CRM up to date?" — the only trustworthy verification is a
human opening the record, which is why all three CHECK tickets specify
push-and-read rather than "res says IN_SYNC".

This matters most for **GAP-095**: an erasure is the one push we cannot
afford to record optimistically, because a false `IN_SYNC` there is a
compliance claim we can't support.

## Proposed fix

Two halves; ours is useless without theirs, so agree the contract first.

**Theirs (Limitless):** the Flow returns a non-2xx, or a 2xx with a
machine-readable error body, whenever a CRM write fails. Cheapest version:
collect each `createRecord`/`updateRecord`/`add_tags` response, and return
`{"ok": false, "errors": [...]}` with a 4xx/5xx when any failed.

**Ours:**

- Parse the response body in `push_sync_record` rather than trusting the
  status line: an `ok: false` (or a non-empty `errors`) is a FAILED push with
  `last_error` populated, and follows the existing retry/backoff path.
- Keep the guarded-write pattern already there (only stamp if the row is
  untouched since this attempt).
- Do not silently succeed on an unparseable body — an unrecognised shape is a
  failure, not an assumption of success, otherwise this regresses the moment
  a Flow is edited.

Worth deciding at the same time whether a push should carry a payload
version/hash so a "verified" state can be re-checked cheaply later, rather
than re-pushing everything.

## Acceptance

- A Flow response indicating a CRM-side failure leaves the `SyncRecord`
  FAILED with `last_error` set, and retries. (test)
- A 2xx with an unrecognised body does not stamp `IN_SYNC`. (test)
- An erasure push (GAP-095) cannot reach `IN_SYNC` without positive
  confirmation. (test, once GAP-095's mechanism is chosen)
- `zoho_backfill`'s SUCCEEDED/PARTIAL/FAILED run summary reflects CRM-side
  outcomes, not just HTTP ones. (test)

## Dependencies

- **Blocked on the response contract with Limitless** — ours is a small
  change once the shape is agreed. The same response carries the record id
  the merged GAP-098 half writes back to `SyncRecord.external_id`.
- **GAP-095** — the erasure case that makes a false `IN_SYNC` a compliance
  problem rather than an accuracy one.
- **CHECK-001 / CHECK-002 / CHECK-003** — until this lands, every "verified"
  in those tickets means a human read the CRM record.


---

## Merged from GAP-098 — The legacy `ZohoId` is never sent, and the Zoho record id is never stored back

> _Folded in 2026-09-16 (todo consolidation). The standalone ticket is closed as
> [GAP-098](done/gap-098-legacy-zohoid-crm-matching.md); the text below is that ticket as it stood, headings
> demoted one level. A reference to GAP-098 elsewhere now means this section._

- **Severity:** 🟠 Gap (duplicate CRM records against the pre-existing
  legacy-synced estate; no round-trip identity).
- **Source:** 2026-09-01 review of Limitless' parse functions against our
  payload builders.
- **2026-09-16 ResProd dry run (supersedes the 2026-09-11 dump figures
  below):** `VillaContact.ZohoId` **carries the column but every value is
  blank**, so the headline conclusion stands — there is no legacy contact
  continuity to preserve, and every contact push INSERTs on first sync
  regardless of this ticket. The rest has moved: `VillaMaster` 112 raw / 76
  matched / 75 loaded (`expected_gap=1`, the 88/339 shared-`ZohoId` pair);
  `VillaEnquire` **2 228** raw / 2 228 matched / 2 227 loaded (`expected_gap=1`,
  enquiries 1267/1268 sharing one id); and — reversing the old claim —
  **`VillaQuotationMaster` DOES have a `ZohoId`, with 1 601 non-blank values**
  and gap 0. `VillaBooking` has the column too (190 non-blank) — it drops out
  of `SPECS` because its **loader is unregistered** (GAP-089), not because the
  schema lacks it. So `SPECS` is four tables, not five, and **no** ResProd spec
  table is missing the column.
- **2026-09-11 loader audit (24-Apr-2025 dump, history):** `VillaContact.ZohoId`
  blank on all 233 rows; `VillaMaster` 75 loaded (112 raw, 36 on deleted
  villas, 1 Temenos duplicate); `VillaEnquire` 44; `VillaQuotationMaster` /
  `VillaBooking` believed to have no column. GAP-108 trimmed `SPECS` and
  rewrote CUTOVER §4b to match the ResProd facts above.
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

### Problem

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

### Proposed fix

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

### Acceptance

- The `external_id` premise is documented — how many rows carry one, and
  whether they resolve in the target org. (investigation, before code)
- Where a legacy `ZohoId` exists, a push updates the pre-existing CRM record
  rather than creating a second one. (verified Zoho-side)
- A create writes the returned Zoho id to `SyncRecord.external_id`. (test)
- A response claiming an `external_id` already held by a different row fails
  loudly rather than stealing it. (test)

### Dependencies

- **GAP-097** — the same response-contract conversation with Limitless;
  settle error reporting and id write-back together.
- **CHECK-001** item 1 / item 9 — the email fallback and the `searchRecords`
  lag are both consequences of having no durable external key.
- **GAP-089** — the spreadsheet historic import creates people (and
  `PastStay` rows, not bookings — shipped 2026-09-02) that may
  correspond to legacy CRM records; worth checking whether it should carry
  `external_id` through.
