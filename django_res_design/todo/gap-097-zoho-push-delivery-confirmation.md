# GAP-097 — A Zoho push is marked `IN_SYNC` on any HTTP 2xx

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
  change once the shape is agreed.
- **GAP-095** — the erasure case that makes a false `IN_SYNC` a compliance
  problem rather than an accuracy one.
- **CHECK-001 / CHECK-002 / CHECK-003** — until this lands, every "verified"
  in those tickets means a human read the CRM record.
