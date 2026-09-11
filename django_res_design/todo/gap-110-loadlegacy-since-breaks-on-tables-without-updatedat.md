# GAP-110 — `loadlegacy --all --since` raises on the third loader: `BaseLoader` assumes every legacy table has `UpdatedAt`

- **Severity:** 🟠 Gap (cutover playbook). `CUTOVER.md` §6's delta-load
  step does not work as written.
- **Source:** GAP-107 unit-1 review (2026-09-10), verified against
  `ResSystem/Database/Data/*.cs`.
- **Files touched (when built):**
  - `django_res/data_migration/base.py` — `since_column: ClassVar[str] =
    "UpdatedAt"` and `_apply_since`, which appends `WHERE/AND <since_column>
    > '<iso>'` unconditionally. Its docstring promises a `-- /*SINCE*/`
    placeholder that is not implemented anywhere.
  - Loaders inheriting the default over tables with **no** `UpdatedAt`:
    `CurrencyLoader` (`VillaCurrency`), `NearbyPlaceTypeLoader`
    (`VillaNearByLocationType`), `FeatureCategoryLoader`
    (`VillaFeaturesCategory`), `ContactLoader` (`VillaContact` has
    `UpdtedAt`, sic), `CollectionLoader` (`VillaCollection`),
    `PropertyFinanceLoader` (`VillaFinance`), `NearbyPlaceLoader`
    (`VillaNearBy`). Others may exist — sweep the registry.
  - `django_res/data_migration/CUTOVER.md` §6 — says loaders without the
    column "will silently ignore the flag"; for `BaseLoader` they raise
    `Invalid column name 'UpdatedAt'` instead.

## Problem

`loadlegacy --all --since '<freeze>'` runs `country`, `region` (fixed in
GAP-107 to use legacy's `UpdateAt` / `DeletedAt` / `CreatedAt`), then
`currency` — which raises on the first query and aborts the delta. The
playbook step has never been exercised end to end. GAP-107 also found that
legacy stamps a **different** column per action on the tables it fixed
(`CreatedAt` on INSERT, `UpdateAt` on UPDATE, only `DeletedAt` on
soft-DELETE), so a single-column filter is blind to inserts and deletions
even where it runs.

## Proposed fix

- `since_column: ClassVar[str | None] = None` on `BaseLoader`; `_apply_since`
  logs `data_migration.since_ignored` (the `rate_rule` precedent) and
  returns the query unchanged when unset, so a loader must **opt in** to
  delta filtering with a column it has verified.
- Per loader, set the real column(s) — reuse `legacy_changed_since_sql`
  (`loaders/_util.py`, GAP-107) where the table has the `CreatedAt` /
  `UpdateAt` / `DeletedAt` triple — or leave it unset and document the
  full-reload behaviour.
- A registry-level test that instantiates every loader with `since=` and
  asserts `_apply_since` produces SQL naming only columns that exist in the
  legacy schema (a checked-in column map, or the live dump under the
  dry-run marker).
- Correct `CUTOVER.md` §6.

## Acceptance

- `loadlegacy --all --since '<iso>'` exits 0 on the 24-Apr-2025 dump.
- Every registered loader either filters on verified columns or logs the
  ignore event; test pins the set.

## Dependencies

- GAP-107 (resolved) — `legacy_changed_since_sql`, the geo precedent.
- Cutover runbook (`CUTOVER.md` §6) — blocked on this if a delta load is
  ever needed after the freeze.
