# FG-002 — `effective()` conflates `""` and `NULL` as "inherit"

- **Severity:** 🟠 Footgun
- **Source:** the 2026-05-26 data-model deep audit §F2
- **Files:** `properties/models/finance.py:36–41`,
  `properties/models/settings.py:79–89`

## Problem

```python
def effective(self, field):
    own = getattr(self, field)
    if own is not None and own != "":
        return own
    return getattr(group, field)
```

For a `CharField(null=True, blank=True)`, both `NULL` and `""` fall
through to the group. A user who *intentionally* clears a property's
override (empty string, not inherit) can't express it — the resolver
always reads `""` as inherit. There's no way to say "this property
explicitly has no bank account note" if the group has one.

## Proposed fix

Pick one of:

1. **NULL is inherit, "" is explicit override.** Make `effective()` only
   short-circuit on `NULL`. Update factories/migrations so today's `""`
   rows that were "really" inherit are converted to `NULL`. Disallow
   `""` at the form layer if we want a clean three-state.
2. **Boolean `<field>_inherits` per inheritable field.** Heavier and
   schema-noisy but unambiguous. Each inheritable field becomes
   `(value, inherits)` where the resolver reads `inherits`.

Recommendation: option 1. Document the contract in the model docstring
and add a service-level migration to normalise existing data.

## Acceptance

- Resolver tests for the three cases: `NULL` → inherit, `""` → empty
  override, value → own.
- Migration normalising current `""` rows (if any) to `NULL`.
- Docstring on `effective()` calls out the contract.

## Dependencies

None — but coordinate with the PropertyFinance / PropertySettings
factories so the new contract is honoured everywhere.
