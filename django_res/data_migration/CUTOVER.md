# Legacy → Postgres Cutover Playbook

This is the ops checklist for the final cutover from `ResSystem/` (.NET 7 +
Azure SQL Edge) to the new Django REST API + Postgres backend.

Run end-to-end **after** a green CI on `main` and a confirmed dry run
against a recent dump. The goal is to land every legacy row that has a
schema home in the new system, with zero unexplained gaps in
`reconcile_legacy`.

## 0. Prerequisites

- A read-only Azure SQL Edge container holding the latest production dump
  (the `res-db` service in `ResSystem/docker-compose.yml`).
- The Villa Collective Postgres DB at the target URL — empty, freshly
  migrated.
- A staff user authorised to run management commands on the production
  cluster.
- `LEGACY_DATABASE_URL=mssql://sa:<pw>@<host>:<port>/NewResSystem`
  exported in the shell.

## 1. Freeze legacy writes

Per ops procedure — typically by switching the legacy app to maintenance
mode. Capture the freeze timestamp; this becomes `--since` if a follow-up
delta load is needed.

## 2. Take the final legacy dump

The current convention is `live-db-YYYY-MM-DD.sql` (UTF-16 LE). Copy it
into the local `ResSystem/Database/` directory.

## 3. Reseed `res-db` from the final dump

```bash
.claude-tmp/drop-and-reseed.sh
```

Wait for the script to report `Restore complete`. Sanity-check that
`SELECT COUNT(*) FROM VillaMaster` returns the expected number of
properties.

## 4. Run every loader

```bash
uv run python manage.py migrate           # applies pending schema migrations
uv run python manage.py loadlegacy --all
```

Expect this to finish in ~2 minutes on the live snapshot. Watch for any
non-zero `errors` column in the per-loader summary; investigate before
proceeding.

## 4b. Verify external-ID continuity (Zoho + WordPress)

Before unpausing any outbound integration tasks, confirm that every
legacy external id has been migrated into `integrations.SyncRecord`.
Dropping these ids causes the first post-cutover sync to duplicate
records on the remote side (Zoho creates new records, orphaning years
of CRM activity; WordPress allocates new posts, breaking already-emailed
booking URLs). See `django_res_design/08-integrations.md` →
"Migrating legacy external IDs" for the full rationale.

```bash
uv run python manage.py reconcile_legacy --integrations
```

The `--integrations` flag extends the normal reconcile output with:

- Per legacy column (`VillaMaster.ZohoId`, `VillaContact.ZohoId`,
  `VillaEnquire.ZohoId`, `VillaQuotationMaster.ZohoId`,
  `VillaBooking.ZohoId`, `VillaBooking.BookingUrl`,
  `VIllaConcierges.Slug`): count of non-blank legacy values vs count of
  matching `SyncRecord` rows.
- For `VillaSyncDetail`: per-`SiteId` row count vs
  `SyncRecord(provider=WORDPRESS_SITE, provider_instance=SiteId)` row
  count.

Any non-zero gap is a **blocker**. Cutover must not proceed until every
external id has been transplanted, or the operator has explicitly
recorded the gap as an accepted loss with a written justification (e.g.
"the 12 archived bookings with stale Zoho ids predate the current Zoho
account and would 404 on push anyway").

**While the gap is non-zero, keep outbound push tasks paused.** Either
set `SyncRecord.status=DISABLED` for the affected providers, or pause
the Celery beat schedule for the `push_*` and `reconcile_*` tasks. Do
not rely on the prod-only environment gate in legacy as a safety net —
the new system pushes from every environment by default.

## 5. Verify with `reconcile_legacy`

```bash
uv run python manage.py reconcile_legacy
```

Every row should have `gap == expected_gap`. **Documented expected losses**
(safe to accept):

| Source table              | Expected gap | Reason |
|---------------------------|--------------|--------|
| `VillaCollectionsMappings`| ~308         | Legacy has duplicate mapping rows for the same (collection, property); collapsed. |
| `VillaFinance`            | ~1236        | 413 contact-default rows mirror onto `GroupFinance` (no 1:1 mapping); 676 parent-child override rows have no schema equivalent. |
| `VillaCurrency`           | ~4           | Junk rows (`HTFG`/`RUPEE`/`RS`) with zero FK references are skipped. |
| `VillaSeasonRate`         | ~3462        | Rows with no price (`NightlyPrice IS NULL AND WeeklyPrice IS NULL AND Price IS NULL AND IsPOA = 0`) are skipped — they were unusable in legacy too. |
| `VillaMaster`             | 1            | One row with empty `Name`. |
| `VillaContactMapping`     | 1            | Composite legacy_id collapse. |

Any other gap is a **blocker**. Track it down before proceeding.

## 6. (Optional) Delta load for late writes

If the freeze in step 1 wasn't perfectly clean, you can run a second pass
restricted to rows updated after the freeze:

```bash
uv run python manage.py loadlegacy --all --since '2026-05-13T17:00:00'
```

Loaders use the legacy `UpdatedAt` column for this filter — a few lookups
without that column will silently ignore the flag.

## 7. England → GB merge

After Phase 1.1 added the canonical `GB` row, the legacy "England"
(iso2 `UK`, legacy_id `24`) row is no longer needed. Merge once:

```bash
uv run python manage.py merge_country --from-legacy 24 --to-iso2 GB
```

Output should report `Rewrote N rows and deleted source country.`

## 8. Image files (out of scope here)

`properties_propertyimage` has ~13 000 filenames pointing at the legacy
`/uploads/` tree; the actual files live wherever ops has them (S3, a
backup tarball, etc.). Copy the binaries into the new storage backend
according to the separate **Image migration workstream**. The DB rows are
already in place.

## 9. Cut DNS / app config

Switch the Villa Collective frontend (and any integrations) to the new
Django backend's base URL. Smoke-test:

- `/api/quotations` returns only real quotations (no synthesised
  `legacy_id` starting `booking-`).
- `/api/countries` returns the canonical ISO-3166 list, including `GB`.
- A staff user can log in and read a property's full detail page.

## 10. Retire the legacy container

After 24–48 hours of clean operation:

```bash
cd ResSystem && docker compose down -v
```

Archive `live-db-YYYY-MM-DD.sql` to the ops data-retention store
(typically S3). Keep the `data_migration/` Python package in the
repo indefinitely — the loaders document the legacy schema and remain the
authoritative migration record.

## Rolling back

If something blocks the cutover after step 4, the new Postgres DB can be
re-seeded any time by:

1. `dropdb villacollective && createdb villacollective`
2. `uv run python manage.py migrate`
3. `uv run python manage.py loadlegacy --all`

All loaders are idempotent (upserts keyed on `legacy_id`), so re-running
from scratch is safe.
