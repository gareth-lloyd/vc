# INV-001 — `PropertyContactAssignment` role / owner uniqueness

- **Status:** ✅ **CLOSED** (2026-05-27 critique) — invariant present.
  `PropertyContactAssignment` carries `role` (ContactRole enum) plus two
  partial `UniqueConstraint`s: `(property, contact, role)` while active,
  and `(property, role)` where `is_primary=True` and active. "Owner per
  property" is enforced via `is_primary`, not role alone — a contact may
  be a non-primary OWNER across multiple groups, but only one OWNER may
  be `is_primary` per property. No follow-up needed.
- **Severity:** Investigation
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` "What I'd
  want to investigate further" item 1

## Question

- Does `PropertyContactAssignment` carry a `role` field with a proper
  enum?
- Is a contact allowed to be `OWNER` on multiple groups, or is "owner
  per property" a uniqueness invariant?

## Suggested probe

```
rg -n "class PropertyContactAssignment" django_res/properties/
rg -n "role" django_res/properties/models/
```

Then check whether the M2M through-model has any
`unique_together`/`UniqueConstraint` on `(property, role)` where role is
the primary-owner sentinel.

## Outcome

Either:

- Confirm the invariant is there and the question is closed.
- Or open a bug/footgun ticket capturing the missing constraint.
