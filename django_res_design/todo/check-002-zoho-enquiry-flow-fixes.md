# CHECK-002 — Zoho enquiry flow: fixes raised with Limitless

- **Severity:** 🔎 Check (external party — closed by verifying someone
  else's change, not by building).
- **Owner of the work:** Limitless (Zoho Flow `limitless_parse_enquiry`).
  Not in this repo.
- **Raised:** 2026-09-01, by email, off the enquiry-sync demo transcript +
  the Deluge parse function.
- **Verify with:** `manage.py zoho_send_sample` against the Limitless
  sandbox, then read the resulting Deals.

## Why this is a check, not a gap

Our payload (`django_res/reservations/services/zoho_payload.py`,
`build_enquiry_payload`) already carries everything below; the defects are in
the Zoho-side mapping. The one item from this review that *is* ours — erasure
propagation — is filed separately as **GAP-095** and deliberately excluded
here.

## Items to verify

1. **Does anything upsert the Deal?** Unlike the contact routine, the parse
   builds a map and returns it with no `searchRecords`/`createRecord`/
   `updateRecord` of its own. Every enquiry create *and* update pushes
   (`reservations/apps.py:249`), so an un-keyed caller means a new Deal per
   save. Asked: confirm what the calling Flow does.
   - *Verify:* push the same enquiry twice; expect one Deal.

2. **Stop writing Contacts from the enquiry flow.** It writes a thin contact
   map (`Phone` ← `primary_phone`) that competes with the dedicated contact
   flow, which routes by label. Asked for: look up by RES_ID and stop; if a
   create is genuinely needed, call the same routine the contact sync uses.
   Two specifics inside it:
   - `contact_id = create_response.get("id")` here vs
     `.get("data").get(0).get("details").get("id")` in the contact function.
     At most one is right; if it's this one, `Contact_Name` is never set.
   - The same email-merge risk as CHECK-001 item 1 — and yes, that scenario
     can occur. The rule must be identical in both places.

3. **`Agency` points at the person, and `agent` is dropped.**
   `enquiry.put("Agency", contact_id)` sets it to the individual's Contact
   record. We send a keyed `agency` sub-object (`RES_ID`/`id`/`name`)
   precisely so it can join the real agency. Separately the whole `agent`
   sub-object (a different Person, with their own agency) is in the ignored
   list — so agent-originated enquiries are indistinguishable from direct
   ones.
   - *Verify:* push an agent-originated enquiry.

4. **Stage collapses three states into one.** `progressing`, `quote_sent`
   and `follow_up` all → "Quoted", flattening the GAP-038/039 funnel and
   hiding backwards moves. Asked for: three stages. Also asked: confirm
   `"Enquiry"` really is the actual_value behind the "Closed Won" label
   **and** that its forecast category is Won — a won deal in a stage Zoho
   treats as open breaks pipeline reporting silently.

5. **`lead_status` is not mapped** — and isn't in their excluded list
   either, so it was missed rather than deferred. `hot`/`warm`/`cold`/`dead`
   (`reservations/enums.py:28`); our own payload docstring says it pushes as
   a CRM tag.

6. **`Enquiry_Source` is hardcoded to "Other".** Known and acknowledged;
   tracked here so it isn't forgotten. Values: `main_website`,
   `agent_portal`, `email_inbound`, `phone`, `other`. Priority rises when the
   WordPress intake goes live (`todo/wp-enquiry-cutover.md`) — source
   attribution is the most valuable segmentation on the object and every lead
   currently looks identical.

7. **Reopened deals keep their `Lost_Reason`.** `Enquiry.reopen()` clears
   `lost_reason` to `""` in the same locked UPDATE as the status change
   (`reservations/models/enquiry.py:424`); the `!= ""` guard discards it, so
   a revived deal sits in an open stage still showing "Availability".
   - *Verify:* mark an enquiry dead, reopen it, push, read the Deal.

8. **`inbound_message` and `notes[]` are both dropped.** The guest's own
   words, and the operator notes we started pushing on 2026-07-23 *keyed by
   RES_ID for Zoho-side dedupe*. Both are in the ignored list, which reads as
   a scope miss. Asked for: `inbound_message` → Deal description, notes →
   CRM notes.

9. **Smaller mapping items.** `Number_of_People` receives `adults` only (a
   4+3 party reads as 4); `Length_of_Stay` goes in as the string
   `"7 nights"`, making it text — no sorting, filtering or averaging;
   `Number_of_Bedrooms` is our *minimum*, not a count, so should be labelled
   accordingly; `Deal_Name` is `"RES Enquiry: <pk>"` for every record when we
   send both `reference` and `full_name`.

## Open decision (not yet a fix)

**Countries of Interest.** The field on our side is a single `region` FK, not
a country — we send `region.name` plus the region's country name and ISO2.
"United Kingdom" being the only value in their test data needs explaining
before anything is seeded. The decision to take: a picklist we seed from our
region list (needs maintaining as we take on properties) vs a plain text
field that accepts whatever we send. Currently unmapped either way, so
nothing is lost while it's open.

## Acceptance

- Each numbered item confirmed against the sandbox by push-and-read.
- The Countries-of-Interest decision recorded here, and the mapping built to
  match it.
- The test batch we asked for has been run: an agent-originated enquiry; one
  reopened after being marked dead; one with operator notes; one whose linked
  person has since been anonymised (expect GAP-095 to be the blocker, not a
  Flow bug); and one pushed twice to prove the Deal dedupes.

## Dependencies

- **GAP-095** — erasure propagation; the anonymised-person case in the test
  batch cannot pass until that is decided.
- **GAP-097** — "verified" means a human read the Deal, not that res said
  `IN_SYNC`.
- **CHECK-001** — item 2 must land the *same* contact rule as CHECK-001
  item 1; fixing one and not the other leaves the merge hazard in place.
