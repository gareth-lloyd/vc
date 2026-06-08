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

## 4b. Capture external IDs into `SyncRecord` (Zoho)

This step **captures** the external ids Zoho already issued against legacy
rows into `integrations.SyncRecord`, while the legacy DB is still readable.
The `syncrecord_zoho` loader runs as part of `loadlegacy --all` in step 4,
so there is nothing extra to run here — this step is the verification.

Why it is time-critical even though nothing syncs yet: the legacy DB is the
only home of these ids and it is decommissioned 24–48h after cutover (step
10). These ids are the routing keys for every future push — when outbound
sync goes live (deferred to v1.1; the engine in `integrations/tasks.py` is
`NotImplementedError` today, so **no push fires at the M1 cutover**), a
missing id makes Zoho INSERT a new record instead of UPDATE, orphaning years
of CRM activity. Capture them now or lose them. See
`django_res_design/08-integrations.md` → "Migrating legacy external IDs".

Verify continuity:

```bash
uv run python manage.py reconcile_legacy --integrations
```

The `--integrations` flag adds, after the main table:

- **Zoho external-ID continuity** (enforced): per source table
  (`VillaMaster`, `VillaContact`, `VillaEnquire`, `VillaQuotationMaster`,
  `VillaBooking`), the count of backfilled `SyncRecord(provider=ZOHO_CRM)` rows
  (with a non-blank `external_id`) vs the number of **loaded** rows that carried
  a legacy `ZohoId` — i.e. legacy rows whose `ZohoId` is non-blank *and* whose
  `legacy_id` resolves to an imported Django row. The raw legacy `ZohoId` count
  is shown alongside (`legacy ext id`) so you can see how many were not imported,
  but the gap is computed against `loaded`: a `ZohoId` on a row the loaders
  intentionally dropped (soft-deleted, empty `Name`, unresolvable FK) has no push
  target, so it is *not* a continuity failure and does not block. A non-zero gap
  is a **blocker** (the command exits non-zero): a loaded row whose `ZohoId` has
  no `SyncRecord` would duplicate on first push. Cutover must not proceed until
  the gap is zero, or the operator records it as an accepted loss with a written
  justification. (The check compares counts, not values; a full `loadlegacy
  --all` refreshes every `external_id`, but a value drifted on a delta-only
  `--since` pass whose `UpdatedAt` did not advance is not caught here.)
- **WordPress surface** (informational only): legacy `VillaBooking.BookingUrl`
  and `VillaSyncDetail` volume. The WordPress backfill is **not built yet** —
  multi-site fan-out needs a `provider_instance` field on `SyncRecord` that
  the model doesn't have. This row reports the surface so it isn't silently
  treated as "all clear"; it never blocks. If WP continuity matters for this
  cutover, that model change and a `SyncRecordWordPressLoader` must land
  first — see `data_migration/WORDPRESS_BACKFILL.md` for the data-shape
  queries to run during this dry-run and the build-vs-descope decision.

Note: there is **no "disable outbound push" step at M1** — there is no push
engine to disable yet. Re-introduce a stop-the-bleeding posture (pause beat,
`SyncRecord.status=DISABLED`) in the v1.1 cutover checklist when `push_*` /
`reconcile_*` actually exist.

## 4c. Quotation-number high-water mark (automatic)

The loaders set `Quotation.number` explicitly from the legacy `QuotationNo`
(so `QVC{number}` / `VC{number}` references keep their exact legacy digits).
Setting the column directly does **not** advance the `quotation_number_seq`
sequence, so the first organically-created quotation after cutover would
otherwise draw a low `nextval` that collides with an already-imported
`QVC2`/`QVC3`/…

`loadlegacy` now fast-forwards the sequence past the highest imported number
automatically at the end of the run (it prints
`Quotation number sequence synced to high-water mark <N>.`), so no manual step
is required. Verify that line appears, then confirm the next organic quotation
lands above the imported range before going live.

If you ever need to re-sync by hand (e.g. after a manual `number` edit), the
equivalent is idempotent — `setval` to the current max is a no-op on re-run:

```bash
uv run python manage.py dbshell -c \
  "SELECT setval('quotation_number_seq', (SELECT COALESCE(MAX(number), 1) FROM reservations_quotation));"
```

## 5. Verify with `reconcile_legacy`

```bash
uv run python manage.py reconcile_legacy
```

The command now enforces this itself: it prints an `expected`/`status`
column and **exits non-zero** if any row's `gap != expected_gap`, so this
step passes iff the command succeeds — no manual cross-reference needed.

The expected-gap numbers live in `reconcile_legacy.py` (`_CHECKS`), which is
their single source of truth. The table below is a human-readable mirror;
if the live dump legitimately shifts a number, change it in the code (that
is where the dry-run calibration happens), not just here.

| Source table              | Expected gap | Reason |
|---------------------------|--------------|--------|
| `VillaCollectionsMappings`| 308          | Legacy has duplicate mapping rows for the same (collection, property); collapsed. |
| `VillaFinance`            | 1236         | 413 contact-default rows mirror onto `GroupFinance` (no 1:1 mapping); 676 parent-child override rows have no schema equivalent. |
| `VillaCurrency`           | 4            | Junk rows (`HTFG`/`RUPEE`/`RS`) with zero FK references are skipped. |
| `VillaSeasonRate`         | 3462         | Rows with no price (`NightlyPrice IS NULL AND WeeklyPrice IS NULL AND Price IS NULL AND IsPOA = 0`) are skipped — they were unusable in legacy too. |
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
according to the separate **Image migration workstream**, tracked as the
legacy-import slice (§11) of
`django_res_design/todo/gap-012-cloudflare-images-hosting.md` (the canonical
home — note the loader flattens `PropertyImages/<VillaId>/<file>` to a flat
`properties/legacy/<file>` key, so the copy must reconstruct the source
subfolder from each row's `property.legacy_id`). The DB rows are already in
place.

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

All loaders are idempotent (upserts keyed on `legacy_id`, or on the
content-type tuple for `syncrecord_zoho`), so re-running from scratch is
safe.
