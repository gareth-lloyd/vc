# GAP-095 — Erasure does not propagate to Zoho CRM

- **Severity:** 🟠 Gap (compliance-adjacent; open design question spanning
  both sides of the integration). No code change until the mechanism is
  agreed.
- **Source:** 2026-08-31/09-01 review of Limitless' Zoho Flow parse functions
  (`limitless_parse_res_contact`, `limitless_parse_enquiry`) against the
  payloads we actually send. Raised with the Limitless dev 2026-09-01.
- **Files touched (ours, when built):**
  - `django_res/integrations/services/zoho_flow.py:162` —
    `is_anonymized_person`.
  - `django_res/integrations/services/zoho_flow.py:223` —
    `enqueue_zoho_push` returns early for an ANONYMIZED `Person`.
  - `django_res/integrations/services/zoho_payloads.py` —
    `build_person_payload` (never reached for an anonymized person).
  - `django_res/reservations/services/zoho_payload.py:200–231` —
    `build_enquiry_payload` blanks the denormalised capture columns and the
    `notes` list when the linked person is erased.
  - `django_res/accounts/models/person.py:205–229` — `Person.anonymize`.
- **Files touched (theirs):** the Flow parse functions above — Zoho-side, not
  in this repo.

## Problem

`Person.anonymize` scrubs PII in res, and the enquiry payload deliberately
blanks its own denormalised capture columns (`first_name`, `last_name`,
`email`, `phone` → `""`, `notes` → `[]`) precisely so the CRM copy can be
scrubbed too. None of that reaches Zoho today, for two independent reasons:

1. **We go silent rather than telling Zoho anything.** `enqueue_zoho_push`
   returns early for an ANONYMIZED `Person`, so the contact push simply stops
   happening. The CRM keeps the last pre-erasure snapshot — name, address,
   emails, phones — indefinitely.
2. **Where a payload *does* still go (the enquiry kind, whose own row isn't
   anonymized), the Flow discards the blanks.** Every field guard in the
   parse functions is "only put the key if it's non-empty", and the enquiry
   parse skips its whole contact block when `person` is null. So the blanking
   we do on purpose is read as "nothing to say about this field".

Two compounding effects:

- **Tags are add-only.** The contact parse calls `add_tags` and never
  `remove_tags`, so the GAP-040 special-category markers (`disability`,
  `approach_with_care`, `past_issues`, `time_waster`) cannot be withdrawn
  from the CRM at all — by erasure or by an ordinary operator edit.
- **`Res_Source_Json` / `RES_Json`.** Both parses stash the entire inbound
  payload in a text field on the record, so a scrub that only cleared mapped
  fields would still leave a full PII snapshot behind. Any erasure mechanism
  has to clear that field too.

## The open question

This is not simply a Flow-side bug, and it shouldn't be filed as one. The
signal we send is ambiguous by construction: an empty string means "cleared"
in the erasure case and "never captured" everywhere else, and the Flow has no
way to tell those apart. Making empty always mean "clear" would fix erasure
and simultaneously start wiping fields that are merely blank in res — which
is exactly the no-clobber behaviour we asked Limitless for on the address
fields.

Options on the table, to settle with Limitless:

- **(a) Explicit erasure signal.** We send a push for the anonymized person
  carrying a flag (`is_erased: true`, or a distinct event kind) that the Flow
  acts on separately from the ordinary field mapping. Keeps "skip empties"
  intact everywhere else. Current preference — needs Flow-side effort
  confirmed.
- **(b) An authoritative-empty field set.** We agree a named list of fields
  where `""` always means clear, and the Flow special-cases them. Cheaper,
  but the list is a drift point and it half-solves the tag problem.
- **(c) Erasure off the upsert path entirely.** A separate delete/scrub call
  (or a manual CRM process with an audit trail) rather than riding the normal
  push.

Whichever we pick has to cover: mapped contact fields, `RES_Json` /
`Res_Source_Json`, tag removal, and the enquiry Deal's denormalised copies.

Note also that an enquiry with **no** linked `Person` has no erasure hook at
all (pre-existing — `Enquiry` has no erasure path of its own; see the
`build_enquiry_payload` docstring). That residual is out of scope here but
belongs in the same conversation.

## Proposed fix

Deferred until the mechanism is agreed with Limitless. Once it is, ours is
roughly:

- Lift the ANONYMIZED early-return in `enqueue_zoho_push` so an erasure
  actually dispatches, replaced by an erasure-shaped payload (option (a)) or
  a scrub call (option (c)) — the early-return exists so `[REDACTED]`
  sentinels never leak, so whatever replaces it must be tested against that.
- Make the erasure push idempotent and replayable via `zoho_backfill`, since
  the first attempt may land while the Flow side is still catching up.
- Confirm delivery properly: the Flow currently ignores every Zoho API
  response and our task marks any 2xx as `IN_SYNC`
  (`django_res/integrations/tasks.py:108`), so a failed scrub would look
  successful. An erasure is the one push we cannot afford to record
  optimistically.

## Acceptance

- Anonymizing a `Person` results in a push (not silence). (test)
- The pushed payload is unambiguous about erasure — a consumer cannot
  confuse it with "these fields were never filled in". (test)
- The erasure payload carries no `[REDACTED]` sentinel or residual PII, and
  no raw-payload snapshot. (test)
- Tag withdrawal is expressible (not only tag addition), for erasure and for
  an ordinary operator tag removal. (test, once the contract is agreed)
- A CRM-side failure to apply an erasure does not leave the `SyncRecord`
  `IN_SYNC`. (test)
- Zoho-side, verified by hand on a sandbox record: mapped fields cleared,
  tags removed, `RES_Json` / `Res_Source_Json` cleared.

## Dependencies

- **Q-010** (guest data retention / GDPR) — the retention policy this serves.
  Q-010 asks *when* we anonymize; this asks *how* that reaches downstream
  systems. Neither is answerable alone.
- **GAP-081** (outbound push) established the ANONYMIZED-skip and the
  enquiry-payload blanking that this ticket revisits.
- **GAP-040** — the special-category tags that make add-only tagging a
  compliance problem rather than a tidiness one.
- **Blocked on a decision with Limitless** (raised 2026-09-01; candidate
  agenda item for the next call). Not actionable until (a)/(b)/(c) is chosen.
