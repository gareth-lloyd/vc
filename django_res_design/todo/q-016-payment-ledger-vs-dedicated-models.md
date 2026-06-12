# Q-016 — Is `Payment` a generic ledger, or the customer-facing money request?

- **Status:** ✅ Resolved 2026-06-12 — **Lane A** (Payment-as-ledger).
  `SECURITY_DEPOSIT` stays in `PaymentPurpose`; cardinality enforced via the
  three per-purpose `UniqueConstraint`s on `Payment` (per the BUG-006
  resolution); `SecurityDeposit` remains the post-capture lifecycle record,
  not a parallel ledger. Recorded in `10-decisions.md` (Live decisions).
- **Severity:** ❓ Open decision (architecture). Upstream of three open tickets.
- **Source:** the 2026-05-26 data-model survey §6.1 (the only survey
  "what could be better" item not yet captured as a ticket).
- **Files:** `payments/models/payment.py` (`purpose` enum incl.
  `SECURITY_DEPOSIT`), `payments/models/security_deposit.py`.

## Problem

Two representations of "money held against damage" co-exist:

- a `Payment` row with `purpose=SECURITY_DEPOSIT`, and
- a dedicated `SecurityDeposit` model with its own lifecycle (returned
  after departure, partial deductions, damage-claim linkage).

Verified still true as of 2026-06-01: `SECURITY_DEPOSIT` is in
`PaymentPurpose` (`payments/enums.py`), and `SecurityDeposit` is a full
model with its own `save()`/reference. Callers must know both exist and
which is authoritative for a given query — the hybrid has the cost of
both and the clarity of neither.

## The decision

Pick one lane:

- **A — `Payment` is a generic ledger.** `SecurityDeposit` becomes a thin
  view/manager over `Payment` rows with `purpose=SECURITY_DEPOSIT`.
  "All money flows for booking X" stays one query; one set of webhook
  handlers and state machines.
- **B — `Payment` is the customer-facing money request.** `SECURITY_DEPOSIT`
  leaves the `purpose` enum and lives entirely in `SecurityDeposit`, which
  has different fields, lifecycle, and reporting needs anyway.

This is the deposit-return / Flywire-hold model question; it needs a human
decision, not a code cleanup.

## Why this blocks other tickets

The shape of the `Payment` constraint set depends on the answer:

- [BUG-006](bug-006-payment-active-purpose-uniqueness.md) proposes a
  SECURITY_DEPOSIT-scoped `UniqueConstraint`. Under lane B that constraint
  moves to `SecurityDeposit` and `SECURITY_DEPOSIT` drops out of the
  uniqueness rule entirely.
- [FG-004](fg-004-payment-purpose-field-coherence.md) proposes per-purpose
  field gating. Lane B removes one purpose from the matrix.
- [BUG-008](bug-008-securitydeposit-damageclaim-fk.md) (the `damage_claim_id`
  fake FK) is squarely inside `SecurityDeposit`; lane A vs B changes whether
  that model is the system of record.

## Acceptance

- A recorded decision (lane A or B) in `product-design/10-decisions.md`.
- BUG-006 / FG-004 / BUG-008 re-scoped to match before any of them lands.

## Dependencies

- Blocks the *final* shape of BUG-006, FG-004, BUG-008 (each can proceed
  on the parts unaffected by the lane choice, but the SECURITY_DEPOSIT
  slice should wait).
- Touches the Flywire integration surface ([GAP-002](gap-002-integrations-empty-url-surface.md)):
  security-deposit holds/releases are Flywire operations.
