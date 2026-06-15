> **✅ RESOLVED (2026-06-15)** — Problem: Customer-facing reference format had to match legacy (VC/QVC). Fix: Added sequence-backed core/refs.py reproducing the legacy format.
>
> _Original ticket preserved below for context._

# GAP-006 — Customer-facing reference format must match legacy (`VC` / `QVC`)

- **Severity:** 🟢 Gap / parity — **product decision made, ready to build.**
- **Source:** user directive "follow the legacy system for anything
  customer-facing" (2026-06); legacy investigation of `ResSystem/`
  (`NewResSystem.Core/Enums.cs`, `Pages/Bookings/BookingInfo.razor`,
  `ResService.cs`).
- **Files:**
  - `core/refs.py:28–40` (`generate_reference`)
  - `reservations/models/quotation.py:20,70–73` (`reference`, `save()`)
  - `reservations/models/booking.py:61,164–167` (`reference`, `save()`)
  - `core/models/system_settings.py` (`SystemSettings` singleton)
  - `data_migration/loaders/finance.py:341` (`QuotationLoader.transform`)
  - `data_migration/loaders/bookings.py` (`BookingLoader` synthesised quotations)
  - design docs (see "Doc reconciliation" below)

## Problem

The spec proposes `BK-12345` / `Q-184`; the code emits `B-2026-NNNNNN` /
`Q-2026-NNNNNN` (via `generate_reference`). **Neither matches legacy.** The
legacy app renders:

- Quotations as **`QVC{QuotationNo}`** (e.g. `QVC1805`)
- Bookings as **`VC{QuotationNo}`** (e.g. `VC1805`) — no hyphen — and
  **carries the quotation number forward**, so a quote `QVC1805` becomes
  booking `VC1805` (same digits, prefix swapped). Prefixes were hardcoded
  constants (`QUOTATION_NO_PREFIX="QVC"`, `BOOKING_NO_PREFIX="VC"`).

Because reference numbers are customer-facing, the rebuild must match legacy,
including continuity for existing references after cutover (an old `VC3679`
must still resolve to the same booking).

## Decision (locked with the user)

1. **Carry forward** — `Booking.reference` is *derived* from its quotation's
   number, not an independent sequence.
2. **Preserve exact legacy numbers on migration** — imported `QVC3679` stays
   `3679`; its booking stays `VC3679`. → dedicated, **sequence-backed
   `Quotation.number`**. (PK-derivation rejected: breaks continuity and
   conflicts with the spec's "reference is separate from the internal PK".)
3. **Prefixes configurable** via `SystemSettings`, defaulting to `VC` / `QVC`.
4. **Scope = Quotation + Booking only.** Enquiry (`E-`), Payment (`P-`),
   Refund (`R-`), SecurityDeposit (`S-`) keep `generate_reference` unchanged.
5. **Direct (non-quote) booking numbering is deferred** — see the open
   sub-question below; interim is a clearly-distinct sentinel.

## Proposed fix — code

**`core/refs.py`** — add three helpers (keep ref logic in one file):
- `quotation_prefix()` / `booking_prefix()` → read
  `SystemSettings.get_solo().settings.get(key, default)` with defaults
  `"QVC"` / `"VC"`.
- `next_quotation_number()` → `nextval('quotation_number_seq')` (atomic,
  concurrency-safe; the `unique` constraint is the backstop).

**`reservations/models/quotation.py`**:
- Add `number = models.PositiveIntegerField(null=True, unique=True)` (NULLs
  distinct in Postgres, so synthesised/interim rows can omit it).
- `save()` (create-only): if `number is None`, `number = next_quotation_number()`;
  then `reference = f"{quotation_prefix()}{number}"`. When `number` is already
  set (migration loaders), **do not** call `nextval`.

**`reservations/models/booking.py`** `save()` (create-only, guarded by
`if not self.reference:` so `_transition`/`modify_*` never recompute):
- `q = self.quotation_line.quotation` → `reference = f"{booking_prefix()}{q.number}"`.
- **Interim fallback** when `q.number is None`:
  `generate_reference("VC-TMP", model=type(self))` → `VC-TMP-2026-123456`.
  Deliberately *not* `VC{digits}`, so the deferred direct-booking decision
  isn't silently pre-empted.
- **Defensive collision suffix**: real flow is 1 quote→1 booking
  (`accept()` selects one line), but if `{prefix}{number}` collides, append
  the existing `_uuid_suffix()` rather than raising.

**Migrations (`reservations/migrations/`)**:
- Schema: add `Quotation.number`; create the sequence via reversible
  `RunSQL("CREATE SEQUENCE quotation_number_seq", "DROP SEQUENCE …")`.
- Data (seed/dev rows): re-derive each quotation's `number`, rewrite to
  `QVC{number}`, then rewrite each booking to `VC{parent.number}`.
  (Dev/staging only — no production yet; the Render demo DB needs this.)

**`data_migration` loaders**:
- `QuotationLoader.transform` → return `number=int(QuotationNo)` and
  `reference=f"QVC{QuotationNo}"` (replacing the `Q-{…:06d}` line).
- `BookingLoader._process_row` → synthesised quotation takes
  `number = legacy VillaBooking.QuotationNo` so the migrated booking becomes
  `VC{QuotationNo}`. **Verify `VillaBooking` exposes `QuotationNo`**; if a
  legacy booking lacks one, fall through to the interim sentinel.
- `data_migration/CUTOVER.md` → document the post-import high-water-mark:
  `SELECT setval('quotation_number_seq', (SELECT MAX(number) FROM reservations_quotation))`.

## Proposed fix — doc reconciliation

`workflows/` and `mock_up_analysis/` already use `VC{QuotationNo}`/`QVC`; only
`product-design/` + top-level `NN-*.md` drifted to `BK-`/`Q-`. Update:
- `product-design/01-domain-model.md` — rewrite the "Reference numbers"
  convention (legacy format, carry-forward, prefixes-in-SystemSettings,
  pointer to the open sub-question); examples `Q-184`→`QVC184`, `BK-2391`→`VC2391`.
  Leave Enquiry `E-1234` as-is.
- `product-design/02-frontend-design.md`, `03-workflows.md`,
  `05-improvements-over-original.md` — swap `BK-`/`Q-` examples → `VC`/`QVC`.
- `05-reservations.md` — Quotation/Booking `reference` field docs → `QVC{number}`
  / `VC{number}`; document `Quotation.number` + carry-forward.
- `mock_up_analysis/02-client-portal.md` (~line 725) — the "pick one" note is
  now resolved; record the decision.
- Final `grep` for stray `BK-` / `Q-1` / `B-2026` / `Q-2026` literals.

## Acceptance

- `Quotation.reference == f"QVC{number}"`; `number` unique + monotonic for
  organic creates.
- Quote-originated `Booking.reference == f"VC{quotation.number}"` (same digits).
- Prefix override via `SystemSettings` is honoured.
- Interim booking (quotation `number=None`) → `VC-TMP-…`, never a bare `VC{int}`.
- Loader maps `QuotationNo → number` and `QVC{QuotationNo}`; migrated booking
  `VC{QuotationNo}`; sequence high-water mark set post-import.
- Tests updated: `reservations/tests/test_quotation.py:43`
  (`startswith("QVC")`), `test_booking.py:352` (`startswith("VC")`); new tests
  for allocation/uniqueness, carry-forward, prefix-from-settings, interim
  fallback, defensive-suffix, loader mapping, `reference` ≤ 32 chars.
- Decision recorded in `product-design/10-decisions.md`.

## Open sub-question (deferred)

**How do NEW direct (non-quote) bookings created in the rebuild UI draw a
reference?** The carry-forward scheme assumes a quotation number; legacy only
referenced quote-originated bookings (`QuotationNo > 0`), showing plain
"Booking Ref" otherwise. Until resolved, the `VC-TMP-…` sentinel holds. (This
is the *new-data* face of the question; migrated legacy bookings are covered
above via their legacy `QuotationNo`.)

## Dependencies

- **Relates to [BUG-007](bug-007-reference-generation-races.md)** (reference
  races + `bulk_create` bypass, currently ✏️ "fix is wrong"). The
  Postgres-`SEQUENCE` approach here is exactly BUG-007's suggested long-term
  fix for the Quotation anchor and sidesteps its TOCTOU race; coordinate so the
  two don't conflict. Booking still allocates in `save()`, so any
  `bulk_create` path for Booking/Quotation remains BUG-007's concern.
- **Sibling of [GAP-005](gap-005-quotation-flow-parity.md)** (Enquiry→Quotation
  flow parity vs legacy).
- Touches `data_migration` cutover — re-run `reconcile_legacy` after loader
  changes (`django_res/CLAUDE.md`).
