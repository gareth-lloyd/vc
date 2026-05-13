# Django REST API

## Local setup

1. `docker compose up -d` (from repo root) — starts Postgres at `localhost:55432`.
2. `cp .env.example .env` (or export `DATABASE_URL` directly).
3. `uv sync`
4. `uv run python manage.py migrate`
5. `uv run pytest` — tests run against the same Postgres instance
   (pytest-django creates and drops `test_villacollective` automatically).

## Legacy data migration

The `data_migration/` app ports the legacy SQL Server dump into the new
Postgres schema. Loaders are idempotent (upserts keyed on `legacy_id`).

- `./manage.py loadlegacy --all` — run every registered loader in
  dependency order. `--since '<iso-8601>'` filters by legacy `UpdatedAt`
  for cutover delta loads.
- `./manage.py reconcile_legacy` — prints a legacy-vs-loaded row-count
  table; documented gaps live in `data_migration/CUTOVER.md`.
- `./manage.py merge_country --from-legacy <id> --to-iso2 <CC>` —
  rewrites FK references via `_meta.related_objects` (same pattern as
  `Contact.merge`) and hard-deletes the source row.

`LEGACY_DATABASE_URL` (`mssql://…`) must be set when running any loader.
See `data_migration/CUTOVER.md` for the full playbook.

## Principles

1. This is a Django REST framework app to support the Villa Collective management suite.

2. **Off-the-shelf over bespoke.** Reach for established libraries (DRF,
   `django-filter`, `dj-rest-auth` / `django-allauth`, `factory-boy`,
   etc.) before writing custom

3. Layered architecture:

- DRF handles serialization and deserialization from HTTP
- ALL business logic needs to be OUTSIDE of the view code, in its own service layer

django_res
./<app>
./services/<service name>
./models/<model name>
./views/<view name>
./tests/

4. One model per file in <app>/models/\*
