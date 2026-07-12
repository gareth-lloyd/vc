> **✅ RESOLVED (2026-07-12)** — all four raw-SQL EXCLUDEs (not just
> pricing's two) ported to `ExclusionConstraint` in model `Meta` (3 TDD
> units, `7cf5eb0..1793daa`): `rateperiod_no_overlap` /
> `rateband_bands_no_overlap` on `RatePeriod`/`RateBand` (inclusive `[]`),
> `booking_no_overlap_blocking` / `bookinghold_no_overlap_live` on
> `Booking`/`BookingHold` (half-open `[)`, conditions on the six blocking
> statuses / `released_at IS NULL`). Names, expression order, and predicates
> byte-identical to the old SQL; both apps' `0003_exclude_constraints.py`
> rewritten in place with `AddConstraint` ops pasted verbatim from
> `makemigrations` (applied DBs keep their record + net schema; fresh DBs
> converge on the same `pg_get_constraintdef`). Range `Func` helpers
> (`DateRangeFunc`/`Int4RangeFunc`) live in `core/fields.py` — the import
> path is frozen into migrations. New repo-wide guard
> `core/tests/test_no_pending_migrations.py` fails the suite on any
> model/migration drift (the ticket's `[]`-vs-`[)` reconciliation stays a
> comment + the pre-existing boundary tests). Owned behaviour change: admin
> saves of overlapping rows now get a form validation error instead of a
> 500. The booking hold constraint name is shared via
> `HOLD_OVERLAP_CONSTRAINT_NAME` (Meta + `HoldService` error mapper).
>
> _Original ticket preserved below (its migration refs pre-date the
> 2026-07 flatten: 0015/0016 became `pricing/migrations/0003`)._

# SMELL-022 — The rate-grid overlap EXCLUDE constraints live only in raw migration SQL; the model layer can't see them

- **Severity:** 🟡 Smell
- **Source:** the 2026-07-02 backend complexity audit (invariants outside the model layer)
- **Files:** `pricing/models/rate.py` (`RatePeriod.Meta` / `RateBand.Meta` —
  CheckConstraints only, no ExclusionConstraint),
  `pricing/migrations/0015_drop_ratecard_contract.py:26–38` (the two
  `btree_gist` EXCLUDEs as raw SQL),
  `pricing/migrations/0016_rename_raterule_to_rateband.py:99–113` (hand-written
  `RENAME CONSTRAINT` forced by the invisibility)

## Problem

The two constraints that actually make the rate grid single-valued —
`rateperiod_no_overlap` and `rateband_bands_no_overlap` (btree_gist EXCLUDEs) —
exist **only as raw SQL inside migration 0015**. `pricing/models/rate.py`
declares only `CheckConstraint`s; there is no `ExclusionConstraint` /
`RangeOperators` anywhere in the model `Meta`.

So the model layer lies about its own invariants: the autodetector can't see
the EXCLUDEs, `makemigrations` never guards them, and a future edit to
`date_from` / `date_to` (or a field rename) won't know a GiST index depends on
it. This already drew blood — `0016` had to hand-write a raw
`RENAME CONSTRAINT` precisely because the rename was invisible to Django.
(Compounding, the EXCLUDE uses inclusive `daterange(..., '[]')` while the
engine prices half-open `[from, to)` nights — the two conventions are
reconciled only by comment.)

## Why it bites

The next schema change to the rate models risks silently dropping or
desyncing the overlap guarantee (the thing that makes ragged/overlapping bands
structurally impossible per GAP-056), and every such change needs a developer
to *remember* the raw-SQL constraint exists. It's a latent "invariant quietly
disappears in a migration" trap.

## Proposed fix

Port both EXCLUDEs to `django.contrib.postgres.constraints.ExclusionConstraint`
in the model `Meta.constraints` (Django supports `daterange`/GiST expressions),
so the model owns them and the autodetector tracks them. Add a comment (or,
better, a test) pinning the inclusive-`[]` vs half-open-`[)` reconciliation
between the constraint and the engine.

## Acceptance

- `RatePeriod` and `RateBand` declare their overlap constraints in
  `Meta.constraints`; `makemigrations` produces no diff and a subsequent field
  edit regenerates/guards them.
- A test asserts overlapping periods/bands are rejected at the DB layer (proves
  the constraint survived the port).

## Dependencies

Related to GAP-056 (introduced the EXCLUDEs) and SMELL-021 (also "pricing
invariant outside the model layer"). No behaviour change intended.
