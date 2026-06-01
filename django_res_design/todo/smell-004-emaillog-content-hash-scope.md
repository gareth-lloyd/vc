# SMELL-004 — `EmailLog` content hash dedupe scope is ambiguous

- **Severity:** 🟡 Smell
- **Source:** the 2026-05-26 data-model deep audit §S4
- **Files:** `comms/models/email_log.py` (and the hash helper /
  signal that populates it)

## Problem

The content hash on `EmailLog` is computed over `(template_key,
sorted(to), correlation)` — **not** the rendered body. Two emails sent
from the same template with the same recipients dedupe even if the
rendered output differs (different `context`). Probably correct, but
the contract is implicit.

## Proposed fix

Either:

1. **Document and pin.** Add a docstring on the hash helper that the
   contract is "one-template-render-per-correlation, not
   one-distinct-body-per-correlation". Add a test pinning the inputs.
2. **Include rendered body in the hash.** If the real intent is
   one-distinct-body-per-correlation, hash on the rendered output too.

Worth confirming with whoever owns comms — `S4` reads like option 1 is
what's wanted, but it's a question.

## Resolution

✅ Chose option 1 (document + pin). Expanded the `_idempotency_hash` docstring
(`comms/services.py`) to state the contract explicitly: dedupe is
**one-template-render-per-correlation**, keyed on `(template_key, sorted(to),
correlation)` only — the rendered `context`/body is deliberately excluded.
Added `test_send_dedupes_across_differing_context` in
`comms/tests/test_email_service.py`: two sends with the same template +
recipients + correlation but different contexts dedupe to one row and one
outbox message (the first render wins). The existing
`test_send_idempotent_on_repeat` already pins recipient-order insensitivity.

## Dependencies

None.
