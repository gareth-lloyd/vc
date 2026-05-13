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

## Conventions

Patterns already in the code. New work should mirror them.

### `legacy_id` on every importable model

`legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)`
on any model with a legacy origin. It is migration metadata only —
never the natural key for application lookups. Use `iso2` for Country,
`code` for Currency, `slug` for Region, etc. Existing examples live on
`accounts.Contact`, `properties.Country`/`Region`, and
`pricing.Currency`.

### Loaders are idempotent upserts keyed on `legacy_id`

Subclass `BaseLoader` (custom transform) or `DeclarativeLoader` (simple
field-rename) in `data_migration/loaders/`. One legacy row → one upsert
via `update_or_create(legacy_id=..., defaults=…)`. Multi-row writes per
legacy row override `_process_row` — see `PropertyLoader` (Property + 4
child writes) and `RoomLoader` (Room + RoomBeds). Register new loaders
in `data_migration/registry.py`.

### Sentinel fallback over silent skip

When a legacy FK can't resolve, fall back to a sentinel rather than
returning `None` and dropping the row. Helpers live in
`data_migration/loaders/sentinels.py`: `unknown_country()`,
`unknown_region()`, `unknown_group()`. Property and Region loaders use
this; new loaders touching geo or group FKs should too.

### Inheritance — call `effective(field)`

`PropertySettings.effective(attr)` and `PropertyFinance.effective(field)`
are the canonical property-→-group resolvers. Don't hand-roll the
chain — wrap them when an outer fallback is needed (see
`_resolve_property_currency` in `data_migration/loaders/pricing.py`).

### FK rewrite + hard-delete merge

The `_meta.related_objects` walk is the canonical way to rewrite FKs
across the schema before hard-deleting a row. References:
`accounts.Contact.merge`, `reservations.Guest.merge`, and the
`merge_country` management command. Always inside
`transaction.atomic()`. Skip `rel.many_to_many` — the through-model FK
shows up separately and gets rewritten there.

### Synthesised rows must not leak into public APIs

`BookingLoader` creates Quotation + QuotationLine rows with `legacy_id`
prefixed `booking-` so legacy bookings can satisfy the PROTECT FK
chain. Any viewset surfacing Quotation/QuotationLine must
`.exclude(legacy_id__startswith="booking-")` in `get_queryset()` — see
`QuotationViewSet` in `reservations/views/quotation.py`.

### Test fixtures — `get_or_create` for canonical countries

Migration `properties.0009` pre-seeds 249 ISO-3166 countries with
`legacy_id=NULL`. Test fixtures must use
`Country.objects.get_or_create(iso2='GB', defaults=…)` — never
`.create(iso2='GB', …)`, which violates the iso2 unique constraint
against the seed. Reference fixtures in `properties/tests/conftest.py`,
`reservations/tests/conftest.py`, `payments/tests/conftest.py`,
`pricing/tests/conftest.py`.

### Validate data-migration changes via `reconcile_legacy`

After changes to loaders or to legacy-importable models, run
`./manage.py reconcile_legacy` and check the gaps against the
documented expected losses in `data_migration/CUTOVER.md`. Unexplained
gaps are a blocker.

### Loader-transform tests prefer hand-rolled dict fixtures

The transform layer is pure (legacy dict → kwargs); test it with dict
fixtures rather than the legacy DB. Reference style:
`data_migration/tests/test_country_loader.py`,
`test_rate_rule_loader.py`, `test_property_loader.py`. Mark
`@pytest.mark.django_db` only when the test exercises the new Postgres
schema (sentinel rows, `get_or_create` semantics).

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
