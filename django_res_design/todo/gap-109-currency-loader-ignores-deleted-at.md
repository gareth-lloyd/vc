# GAP-109 — `CurrencyLoader` never sees `DeletedAt`, so every legacy currency loads active

- **Severity:** 🟡 Gap (cutover fidelity, small). Backend `data_migration/`.
- **Source:** GAP-107 exploration (2026-09-10) — same shape as the GAP-107
  geo fix, deliberately left out of that ticket because it touches currency
  selectability for live rate plans.
- **Files touched (when built):**
  - `django_res/data_migration/loaders/lookups.py` — `CurrencyLoader`
    (`DeclarativeLoader`): `transform_extra` sets
    `is_active = not bool(row.get("DeletedAt"))`, but the generated
    `SELECT <field_map columns> FROM VillaCurrency` never selects
    `DeletedAt`, so the value is always `None` and every row loads active.
  - `django_res/data_migration/management/commands/reconcile_legacy.py` —
    the `Currency` check (`expected_gap=4`, junk rows).

## Problem

Legacy soft-deletes currencies (`DeletedAt` / `DeletedBy`, like every other
lookup). The loader intends to retire them (`is_active = not DeletedAt`)
but never reads the column, so a currency deleted in legacy is offered in
every currency picker (`Currency.is_active` gates usage) and can be chosen
for a new rate plan. The 24-Apr-2025 dump's deleted-currency count is not
yet measured; the GAP-107 census script (`DRYRUN_LOG.md` run 3) is the
one-liner to reuse.

## Proposed fix

- Override `legacy_query` on `CurrencyLoader` to select `DeletedAt` and
  `DeletedBy`, and use `legacy_row_deleted(row)` (`loaders/_util.py`,
  GAP-107 — the OR predicate both legacy conventions satisfy). Retire, never
  skip: rate plans and bookings may reference the row.
- **Check first** whether any live `VillaSeason` / `VillaBooking` /
  `VillaQuotationDetails` row references a deleted currency; if so, decide
  whether the plan's currency should stay selectable (a retired currency on
  a live plan is readable but not offered for new plans — the GAP-102
  meaning of `is_active`).
- Add a `Currency (active)` parity check in `reconcile_legacy` on the
  GAP-107 `Country (active)` pattern, calibrated at the next dry-run.

## Acceptance

- A `VillaCurrency` row with `DeletedAt` set loads `is_active=False`
  (transform test on a dict fixture).
- `reconcile_legacy` `Currency (active)` gap explained and pinned on a live
  dry-run; existing `Currency` gap of 4 unchanged.

## Dependencies

- GAP-107 (resolved) for `legacy_row_deleted` / `legacy_deleted_sql`.
- GAP-014 currency chain (`resolve_property_currency` prefers live plans —
  a retired currency on the preferred plan still wins; confirm that is
  intended).
