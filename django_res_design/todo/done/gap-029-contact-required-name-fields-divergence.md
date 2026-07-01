# GAP-029 — Contact first_name/last_name FE/BE required-field divergence

> ✅ **RESOLVED (2026-07-01)** — **Problem:** `Person.first_name`/`last_name`
> were `CharField` without `blank=True`, so DRF's `ModelSerializer` treated both
> as required and 400'd a company/agency-only contact — diverging from the FE
> `contactWriteInputSchema`, which already refined to "name OR agency". **Fix:**
> added `blank=True` to both name fields (migration `accounts/0015`, state-only
> AlterField) and a name-OR-agency floor at the top of
> `ContactSerializer.validate()` reading the effective (attrs-over-instance)
> value of all three fields, so a PATCH that clears names but leaves the agency
> still passes. App-level gate (mirrors the sibling channel-contactability
> floor), **not** a DB `CHECK` — avoids a migration over audited/anonymized/
> legacy rows; error keyed on `first_name` to render inline under the FE name
> field. FE unchanged (schema + en/el i18n + tests already shipped the rule).
> Decision recorded in `10-decisions.md` (Live decisions). **Commits:** `2a7fee7`
> (backend), `15edeb3` (decision doc). Body retained for context.
>
> ▶️ **UNBLOCKED (2026-06-23) — the blocker has landed.** This was deferred
> behind GAP-045/046; both are now in `done/`: `Contact` was renamed/unified to
> **`accounts.Person`** and **`Organisation`** shipped as a first-class entity
> (`accounts/models/organisation.py`, full stack). The "wait for the unified
> model" rationale is spent — the standalone loosening is no longer throwaway.
>
> **The live bug still exists.** `accounts/models/person.py:28-29` still declares
> `first_name`/`last_name` as `CharField` **without** `blank=True`, so a
> company-only contact still **400s** today. Now actionable: add `blank=True`
> (+ migration) and a name-OR-organisation `validate()`, with tests on both
> layers. Paths below are pre-rename; current targets are `person.py` /
> `accounts/serializers/person.py`. Body retained for context.

- **Severity:** Gap (data-quality / contract divergence) — **live 400, now unblocked**
- **Source:** spun out of GAP-027 during the 2026-06-11
  add-property-flow critique.
- **Files:**
  `frontend/src/features/contacts/schemas.ts`
  (`contactWriteInputSchema`, ~35-50),
  `django_res/accounts/models/person.py` (`first_name`/`last_name`, ~28-29;
  was `models/contact.py`),
  `django_res/accounts/serializers/person.py`

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
