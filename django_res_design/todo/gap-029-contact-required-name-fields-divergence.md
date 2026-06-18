# GAP-029 — Contact first_name/last_name FE/BE required-field divergence

> ⏸️ **DEFERRED — blocked on GAP-045/046 (Person/Organisation); do not close
> until the unified model lands (2026-06-18).** The divergence exists because the
> FE allows *company-only* contacts while the BE `Contact` requires
> `first_name`/`last_name`. It dissolves under the unified-`Person` model: a
> company becomes a first-class **`Organisation`** (GAP-046) and a `Person`
> always has a name — so "company-only contact" stops being a `Person` shape.
> But GAP-045/046 are **design-complete and uncoded** (likely months out), so a
> standalone backend loosening now (`blank=True` on an audited/PII model + a
> name-or-company validator) would be throwaway, and closing this would make a
> **live bug** look resolved.
>
> **Known live friction (documented, not silent):** creating a company-only
> contact **fails with a 400** today and stays broken until Person/Organisation
> ships. Kept open in `todo/` deliberately; fold into GAP-046 when it lands. The
> body below is retained for context.

- **Severity:** Gap (data-quality / contract divergence)
- **Source:** spun out of GAP-027 during the 2026-06-11
  add-property-flow critique.
- **Files:**
  `frontend/src/features/contacts/schemas.ts`
  (`contactWriteInputSchema`, ~35-50),
  `django_res/accounts/models/contact.py` (~26-27,
  `first_name`/`last_name`),
  `django_res/accounts/serializers/contact.py`

## Problem

The FE `contactWriteInputSchema` makes `first_name`, `last_name` and
`company` all optional and only requires **name OR company** — so a
company-only contact passes the FE refine. But the backend `Contact`
model declares `first_name`/`last_name` as `CharField` **without**
`blank=True`, so DRF's `ModelSerializer` treats both as **required** and
rejects a company-only payload with `field_errors`. `company` itself
**is** `blank=True` (genuinely optional). The FE "name OR company" rule
therefore diverges from the BE "first_name AND last_name required" rule.

This blocks the company-only / minimal-contact creation the loader needs,
and the 2026-06-11 email confirmed that company should **not** be
required.

## Proposed direction

This is a **decision** to record, not just a fix.

- **Preferred:** loosen the backend to match the FE — add `blank=True`
  to `first_name`/`last_name` (plus migration), and add a
  serializer/model `validate()` enforcing the name-OR-company rule, with
  tests on both sides. Note this touches a **PII / AUDITED** model
  (`Contact` has `anonymize()` and is audit-tracked), so handle the
  migration and validation carefully.
- **Alternative (rejected):** tighten the FE to require both names —
  rejected because it contradicts the transcript's "NA company" pain and
  the 2026-06-11 email.

## Acceptance

- FE and BE agree on the contract.
- A company-only (or single-name) contact can be created end-to-end.
- Decision recorded in `10-decisions.md`.
- Tests on both layers.

## Dependencies

Spun out of GAP-027.
