> **✅ RESOLVED (2026-06-23)** — Decision (with user): `DamageClaim` **is in
> v1** — shipped the "fuller" model in `reservations/`
> (`reservations/models/damage_claim.py`, migration 0037: reference sequence,
> booking + currency FKs, amount/status/description, `itemized_lines`/`photos`
> JSON scaffolds, `accepted_by_guest_at`; audited) and converted
> `SecurityDeposit.damage_claim_id` → a real
> `ForeignKey("reservations.DamageClaim", on_delete=SET_NULL)` (payments 0009).
> `SecurityDepositService.claim()` resolves the API's PK/instance/None into a
> booking-matched claim, raising `DomainValidationError` (400) on a bad/foreign
> reference so the integrity hole is a clean 400, never a 500. The damages
> workflow itself — operator report sub-form, photo upload, threshold
> permissions, the damages email, the enforced approval state machine — stays
> **deferred to workflow 8/17**. Commits: ded547d, 61d5810, 8d5f914.
>
> _Original ticket preserved below for context._

# BUG-008 — `SecurityDeposit.damage_claim_id` is a hand-rolled FK without integrity

- **Severity:** 🔴 Bug
- **Source:** the 2026-05-26 data-model deep audit §B8
- **Files:** `payments/models/security_deposit.py:71–72`

## Problem

```python
# TODO: convert `damage_claim_id` to FK("reservations.DamageClaim", on_delete=SET_NULL)
damage_claim_id = models.PositiveBigIntegerField(null=True, blank=True)
```

No FK constraint, no cascade, no `select_related`. If `DamageClaim` rows
are deleted (or were never created because the model hasn't shipped),
`damage_claim_id` points at nothing and queries return silent-empty.

## Proposed fix

Two paths depending on whether `DamageClaim` is in scope for v1:

- **`DamageClaim` is in scope:** ship the model, then convert the field
  to `ForeignKey("reservations.DamageClaim", on_delete=SET_NULL,
  null=True, blank=True)`. Data migration: backfill from any existing
  `damage_claim_id` values (or null them if no matching rows exist).
- **`DamageClaim` is NOT in v1 scope:** remove the field altogether and
  the dead TODO. Re-add as a proper FK when the feature lands. The
  current state is the worst of both worlds.

Surface the decision to the user before implementing — this ties into
the broader cancellation/refund flow (workflow 8 / 17).

## Acceptance

- Either an FK with `on_delete=SET_NULL` and a passing migration, or
  field removed + a follow-up ticket noting when to add it back.
- No production rows orphaned.

## Dependencies

Decision: is `DamageClaim` in v1? Likely a question for the user; see
`q-*` tickets if a verification.md entry covers it.
