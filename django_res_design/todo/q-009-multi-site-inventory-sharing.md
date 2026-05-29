# Q-009 — Multi-site inventory sharing

- **Status:** ✅ **RESOLVED** (2026-05-27 critique) — `10-decisions.md`
  Deferred: "WordPress → Canary bidirectional sync; multi-site fan-out
  — Single public site for v1." `02-properties.md` drops
  `VillaSite`/`VillaMapping` as legacy duplicates. v1 is effectively
  single-site; `Booked-VC` carries over only as a status enum value for
  legacy data.
- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 9
- **Blocks:** `Property ↔ Site` relationship, `Booked-VC` semantics

## Question

The legacy `VillaBooking` had a `Booked-VC` status indicating a booking
from another VC site. The new design carries this over. Confirm:

- Do sites really share inventory — one villa visible on multiple
  branded sites?
- Or is each villa exclusive to one site?

If shared, the `Property ↔ Site` relationship should be M2M; if
exclusive, it's a single FK.

## Follow-up once answered

- Lock the relationship shape in `02-properties.md` and the
  availability / quotation queries.
