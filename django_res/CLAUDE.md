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

### State-mutating services accept `idempotency_key`

Any service that *creates* a row in response to an external trigger
(webhook, scheduled job, operator UI submit) takes an optional
`idempotency_key: str | None` and short-circuits the second call.
Webhooks retry, operators double-click — the second call must be a
no-op that returns the original row, not a duplicate write.

Implementation lives in `core/idempotency.py`:

- `find_by_meta_key(queryset, key)` looks up an existing row keyed by
  `meta["idempotency_key"]`. Scope the queryset before calling (one
  booking, one provider — not the whole table).
- `stamp_meta(meta, key)` returns a fresh `meta` dict with the key
  stamped on it; pass straight to `.create()`.

`None` means "no idempotency requested" — internal callers (tests,
management commands, ad-hoc shell) stay ceremony-free.

Some entry points have a natural idempotency key already: a `Booking`
is uniquely tied to a `QuotationLine`, so
`BookingService.create_from_quotation_line` checks for an existing
booking by FK before opening a new one. Prefer the natural key when it
exists; fall back to the `meta` key otherwise.

Reference implementations: `RefundService.request`,
`RefundService.execute`, `BookingService.create_from_quotation_line`.

### Service-layer permission checks

State-mutating services take an `actor` kwarg and call
`actor_has_perm(actor, perm)` (from `core.api.permissions`) for every
transition. `actor=None` is the documented sentinel for system callers
(tests, management commands, background workers) and is granted
unconditionally.

Reference implementation: `payments/services/refund.py`.

### AuditLog registration is part of model definition

Any model whose business-logic docstring or anonymisation flow claims an
AuditLog trail — and any PII-bearing or money-bearing model — must be
registered via `core.audit.track(Model, fields=[...], sensitive=[...])`
in its app's `AppConfig.ready()`. Treat registration as load-bearing
alongside the migration that creates the model.

Field lists stay tight: track lifecycle, PII, and money columns; skip
chatty timestamps (Django's `auto_now` already noises every save) and
free-form JSON blobs whose internal shape isn't actionable in an audit
review (e.g. `Booking.pricing_snapshot`).

`core/tests/test_audit_registry.py` pins the registered set. To
deregister, update `EXPECTED_TRACKED_MODELS` in the same commit and
explain the call in this file.

### Viewset querysets declare their FK reads

Every `ViewSet.get_queryset()` must `select_related()` the FKs the serializer
walks and `prefetch_related()` the reverses / m2m it walks. The list endpoint
must serve a single row and a hundred rows in the same constant query count.
A bare `Model.objects.all()` is a bug even when the current serializer
returns FKs as PKs — the moment someone adds a nested representation or a
`SerializerMethodField` the N+1 lurks.

Pin the bound with `core.tests.assert_max_queries` in a regression test
on at least one list endpoint per app:

    from core.tests import assert_max_queries

    with assert_max_queries(10):
        api_client.get("/api/v1/payments")

Reference: `payments/views/payment.py`, `payments/views/refund.py`, and the
existing `select_related` discipline in `reservations/views/booking.py`,
`properties/views/property.py`, `pricing/views/rate.py`.

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

### API versioning

v1 is mutable while the only consumer is the in-house SPA. Breaking
changes (renamed/removed fields, changed status codes, changed error
shapes) require a note in the commit message and a corresponding
frontend PR landing in the same window. The trigger to fork `/api/v2/`
is *"the API gets a second consumer we don't control"* — until then,
edit v1 in place rather than versioning forward.

### List / detail / write serializer split

Prefer separate serializers when the read response would otherwise carry
write-only fields, when nested reads are heavier than the write payload,
or when list and detail want different depth (e.g., list shows guest
name; detail nests full guest). Reuse a single serializer only when read
and write shapes are identical. Reference:
`reservations/views/booking.py` (`BookingListSerializer` /
`BookingDetailSerializer` / `BookingWriteSerializer`).

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
