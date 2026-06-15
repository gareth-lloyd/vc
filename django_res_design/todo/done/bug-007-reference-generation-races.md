> **✅ RESOLVED (2026-06-15)** — Problem: Reference generation raced under concurrency and was bypassed by bulk_create. Fix: Switched to a DB sequence with db_default on Enquiry/Payment/Reservation/SecurityDeposit references.
>
> _Original ticket preserved below for context._

# BUG-007 — Reference generation races and is bypassed by `bulk_create`

- **Severity:** 🔴 Bug
- **Status:** ✅ resolved — `feat/reference-sequence`, merged `e62a087`.
- **Source:** the 2026-05-26 data-model deep audit §B7
- **Files:** `core/refs.py:28–40`, `payments/models/payment.py:119–122`
  (and any other anchor that calls `generate_reference`)

## Problem

Three stacked issues in `generate_reference`:

1. **TOCTOU race.** Two requests in the same millisecond both pass the
   "not exists" check and both insert. Saved by the `unique=True` on
   `reference`, but the caller sees a 500.
2. **Single-shot retry.** On collision the fallback is a UUID-suffix
   candidate; if *that* collides (rare but possible) there's no retry —
   straight to `IntegrityError`.
3. **`bulk_create` bypass.** `save()` is the only place references get
   set. `bulk_create([Payment(), Payment()])` inserts with `reference=""`,
   which violates `unique=True` on the second row. This is a real risk
   for the data-migration loaders.

## Proposed fix

> **Superseded — the original `pre_save` idea below was wrong.** `bulk_create`
> skips signals just as it skips `save()`, so a signal would not fire on the
> exact path the bug is about. The only place a fix can live that *nothing*
> bypasses is the database itself.

**Implemented (feat/reference-sequence):** move allocation into the column's
`db_default`, backed by a per-series Postgres `SEQUENCE`. The DB stamps
`{prefix}-{year}-{nextval}` on every insert path — `save()`, `bulk_create`,
raw SQL. The sequence guarantees uniqueness, so the TOCTOU race and the
single-shot retry both vanish (no retry loop needed). An explicit `reference`
(legacy loaders) still wins; the default only fills a blank.

- `core/refs.py`: `reference_db_default(prefix, sequence)` (the Concat/nextval
  expression) and `create_sequence_sql(seq, table, column)` (the DDL helper).
- Field gains `db_default=reference_db_default("P", sequence="payment_reference_seq")`
  on Payment / Refund / SecurityDeposit / Enquiry; the `save()` ref-stamping
  overrides are deleted.
- One migration per app creates the sequence (`OWNED BY` the column) *before*
  the `AlterField` that wires the default.
- `PaymentScheduler` loses its hand-rolled pre-`bulk_create` UUID stamping
  (now redundant); it re-fetches the DB-assigned references onto the returned
  rows.

Quotation/Booking already use the `quotation_number_seq` pattern (legacy
`QVC`/`VC` parity) and are unchanged. `generate_reference` survives only as
Booking's interim fallback for a numberless quotation.

**Format change:** the `P`/`R`/`SD`/`E` suffix moves from a random-ish
ms/UUID tail to the sequence value (`P-2026-1`, `P-2026-2`…) — consistent with
the already-sequential `QVC`/`VC` refs, mildly enumerable (reveals volume).
These prefixes are new-build (no legacy format to match); `payment_reference`
is customer-facing (payment receipt email).

## Acceptance

- `pre_save` signal stamps `reference` on `bulk_create` paths (test:
  `Payment.objects.bulk_create([..., ...])` produces two distinct
  references).
- Test: simulated collision retries and eventually succeeds.
- Loader regression: replay the data-migration `PaymentLoader` against a
  fresh DB and confirm no `IntegrityError` on duplicate references.

## Dependencies

Audit the other anchors that use `generate_reference` (Quotation,
Booking, …) and make sure the signal pattern covers them too.
