# SMELL-004 — `EmailLog` content hash dedupe scope is ambiguous

- **Severity:** 🟡 Smell
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` §S4
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

## Dependencies

None.
