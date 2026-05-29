# Django REST API

## Local setup

1. `docker compose up -d` (from repo root) — starts Postgres at `localhost:55432`.
2. `cp .env.example .env` (or export `DATABASE_URL` directly).
3. `uv sync`
4. `uv run python manage.py migrate`
5. `uv run pytest` — tests run against the same Postgres instance
   (pytest-django creates and drops `test_villacollective` automatically).

## Environments

Settings modules in `villacollective/settings/`:

- `base` — shared; `SEED_DEV_ALLOWED = False`.
- `dev` / `test` — local + CI; `SEED_DEV_ALLOWED = True`.
- `production` — real production; inherits `base` (seeding stays blocked).
- `staging` — **Render**. Inherits `production` (so `DEBUG=False`, SSL
  redirect, secure cookies, env-driven secrets all hold), but sets
  `SEED_DEV_ALLOWED = True` so the Render demo DB can be populated with
  `seed_dev`. The Render `villacollective-api` service runs this module
  (`DJANGO_SETTINGS_MODULE` in `render.yaml`).

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

### Booking creation must create the LEAD `BookingGuest`

`Booking.guest` is a denormalised pointer to the LEAD `BookingGuest` row,
kept in sync by `_booking_guest_post_save`. The denorm is for read-side
performance only — the canonical source of truth is the `BookingGuest`
table, which encodes the full multi-contact set (LEAD, CO_TRAVELLER,
PAYER, CC_ONLY).

Any code path that creates a `Booking` must also create a matching
`BookingGuest(role=LEAD)` row inside the same `transaction.atomic` —
otherwise the LEAD invariant is inert and `booking.booking_guests.filter(
role=LEAD)` returns empty even though `Booking.guest` is populated. The
`_booking_guest_pre_delete` orphan guard raises `LeadGuestProtectedError`
if you try to delete a LEAD row while its booking still exists; the
canonical "swap LEAD" pattern is to demote the old LEAD to `CO_TRAVELLER`
and create the new LEAD row inside one atomic block.

Reference implementations: `BookingService.create_from_quotation_line`,
`data_migration/loaders/bookings.py` `BookingLoader._process_row` (uses
idempotent `get_or_create` so re-runs don't double up).

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

### Realistic test data — `factory-boy` factories + `seed_dev`

Each app owns a `factories.py` of `factory-boy` factories
(`properties/`, `pricing/`, `accounts/`, `reservations/`). They are the
single source of test-data builders: pytest fixtures and the `seed_dev`
command both compose them, so a builder is exercised the same way in
tests and in a populated dev DB.

`./manage.py seed_dev [--scale small|medium|large] [--properties N]
[--bookings N] [--seed S] [--i-understand]` generates realistic
dev/staging data. It is **additive** — every run appends a fresh batch
and never truncates. The transactional graph
(Enquiry → Quotation → Booking → Payment) is built through the real
service layer (`QuotationService`, `BookingService`, `PaymentScheduler`,
`SecurityDepositService`), so statuses, events, holds and pricing
snapshots are production-faithful; a fraction of bookings are walked
down the state machine for status variety.

Conventions baked in — mirror them in new factories:

- **Cross-run uniqueness.** `factory.Sequence` is an in-process counter,
  *not* unique across runs. Unique fields combine the per-process
  `RUN_TOKEN` (a uuid defined in `properties/factories.py`, imported by
  the sibling factories) with the sequence, so additive runs never
  collide on a unique constraint (slug, email, phone).
- **Respect seeded/canonical rows.** Factories for migration-seeded or
  canonical models (`CountryFactory`, `CurrencyFactory`,
  `PropertyCategoryFactory`, `TermsVersionFactory`) use
  `django_get_or_create` so they reuse the seeded row instead of
  fighting its unique constraint — the analogue of the `get_or_create`
  fixture rule above.
- **Production block.** Guarded by `settings.SEED_DEV_ALLOWED` (False in
  `base`/production, True in `dev`/`test`/`staging`). `--i-understand`
  documents intent only — it does **not** bypass the production block.

Reference: `django_res/core/management/commands/seed_dev.py`,
`properties/factories.py`, and the per-app `tests/test_factories.py`.

### Villa image pool — manifest-driven seed imagery

`seed_dev` draws property imagery *and* property identity from a committed
pool of villa images under `core/seed_data/villa_images/`, so dev/staging
catalogue/detail screens render real villas instead of grey 1×1
placeholders. `manifest.yaml` is the single source of truth: one entry per
villa with `slug`, `display_name`, `location_tag`, `country_iso2`,
`style_anchor`, and per-kind `prompts`. Each entry owns a subdirectory of
`hero.jpg` / `interior.jpg` / `exterior.jpg` / `gallery.jpg` (no floor
plans — the model produces poor ones; `FLOOR_PLAN` falls back to the 1×1
placeholder).

How it wires together (mirror this if you extend it):

- `properties.factories.villa_manifest()` returns the manifest entries that
  have a `hero.jpg` on disk. The `properties` seed stage cycles that list,
  **exhausting every villa before any repeat**, and builds each property's
  `display_name` / `region` / `country` (loud `Country.objects.get` on the
  seeded ISO row) / description from the entry.
- `PropertyFactory` writes the HERO via the `children__villa` post-gen
  kwarg; the `gallery` stage writes the non-HERO images from the *same*
  villa, tracked on `SeedContext.property_villa` (pk → slug). Image bytes
  are memoised per `(slug, kind)`. Missing files / non-manifest properties
  fall back to the 1×1 placeholder, so a checkout without the pool (and the
  `tests/test_factories.py` cases) still works — they `pytest.skip` when the
  pool is absent.

Regenerate / expand the pool with the one-off command (writes the working
tree, not the DB; **not** gated by `SEED_DEV_ALLOWED`):

`./manage.py generate_seed_images [--only <slug>] [--kind <hero|interior|
exterior|gallery>] [--quality <low|medium|high|auto>] [--dry-run] [--force]`

It builds each image from the manifest via OpenAI `gpt-image-1`
(`1536×1024`, 3:2), re-encodes to ~1200 px JPEG q80 with Pillow, is
idempotent (skips existing files unless `--force`), and refuses to run
without `OPEN_AI_API_KEY`. That key (and any local secret) is read from the
**repo-root `.env`**, loaded by `villacollective/settings/base.py` via
`environ.Env.read_env(BASE_DIR.parent / ".env")`.

Reference: `core/management/commands/generate_seed_images.py`,
`core/seed_data/villa_images/{manifest.yaml,README.md}`,
`core/seed/stages/{properties,gallery}.py`.

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
