# Django REST API

## Local setup

1. `docker compose up -d` (repo root) — Postgres at `localhost:55432`.
2. `cp .env.example .env` (or export `DATABASE_URL` directly).
3. `uv sync && uv run python manage.py migrate`
4. `uv run pytest` (pytest-django creates the test DB automatically).

From the repo root, `make test-backend` runs the backend suite and `make test`
runs backend + frontend together.

## Background tasks (Celery)

Redis broker (`redis` service in `docker-compose.yml`; Render Key Value in
prod); no result backend — tasks are fire-and-forget. App object in
`villacollective/celery.py`. Run locally (after `docker compose up -d`):
`uv run celery -A villacollective worker -l info` (+ `beat` for the scheduler).

- Tasks live in `<app>/tasks.py` under `@shared_task` (autodiscovered; stay
  plain callables).
- Periodic schedule is static in `settings/base.py` (`CELERY_BEAT_SCHEDULE`,
  UTC). Schedule only *implemented* tasks — a scheduled stub errors every
  beat tick.
- Tests run eager (`CELERY_TASK_ALWAYS_EAGER`). Service-layer dispatch goes
  through `transaction.on_commit`, so a test asserting a synchronous send needs
  `pytestmark = pytest.mark.usefixtures("run_on_commit_immediately")`
  (fixture in `django_res/conftest.py`).

## Tests

- Parallel by default (`pytest-xdist`, `-n auto` in `addopts`); each worker
  gets its own `test_villacollective_gw{n}` DB, so isolation matches a serial
  run. Pass `-n0` for the single-test TDD inner loop (readable output, live
  progress, clean `-x`).
- `--reuse-db` is on by default; pass `--create-db` after changing migrations.
- A linked git worktree (sibling `../villacollective-worktrees/<slug>/`)
  automatically gets its own `test_villacollective_<hash>` DB
  (`settings/test.py` detects the worktree via its file-pointer `.git`; override
  with `PYTEST_DB_SUFFIX`), so concurrent worktrees don't collide on the shared
  Postgres container.
- Local Postgres runs `fsync=off` (test-speed convenience) — never copy those
  flags to a database you can't recreate.

## Environments

Settings modules in `villacollective/settings/`: `base` (shared,
`SEED_DEV_ALLOWED = False`), `dev` / `test` (local + CI, seeding allowed),
`production`, and `staging` (Render — inherits `production` so all hardening
holds, but allows `seed_dev`; wired via `DJANGO_SETTINGS_MODULE` in
`render.yaml`).

## Legacy data migration

`data_migration/` ports the legacy SQL Server dump into Postgres; loaders are
idempotent upserts keyed on `legacy_id`. `LEGACY_DATABASE_URL` (`mssql://…`)
must be set for any loader. Full playbook: `data_migration/CUTOVER.md`.

- `./manage.py loadlegacy --all` — every loader in dependency order
  (`--since '<iso-8601>'` for cutover delta loads).
- `./manage.py reconcile_legacy` — legacy-vs-loaded row-count table.
- `./manage.py merge_country --from-legacy <id> --to-iso2 <CC>`.

## Conventions

Patterns already in the code. New work should mirror them.

### `legacy_id` on every importable model

`legacy_id = CharField(max_length=64, null=True, blank=True, db_index=True)`
on any model with a legacy origin. Migration metadata only — never the
application lookup key (use `iso2` for Country, `code` for Currency, `slug`
for Region, …). Examples: `accounts.Contact`, `properties.Country`.

### Loaders are idempotent upserts keyed on `legacy_id`

Subclass `BaseLoader` (custom transform) or `DeclarativeLoader` (simple
rename) in `data_migration/loaders/`; one legacy row →
`update_or_create(legacy_id=…, defaults=…)`. Multi-row writes override
`_process_row` (see `PropertyLoader`, `RoomLoader`). Register in
`data_migration/registry.py`.

### Sentinel fallback over silent skip

When a legacy FK can't resolve, fall back to a sentinel rather than dropping
the row — helpers in `data_migration/loaders/sentinels.py`
(`unknown_country()`, `unknown_region()`, `unknown_group()`).

### Inheritance — call `effective(field)`

`PropertySettings.effective(attr)` / `PropertyFinance.effective(field)` are
the canonical property→group resolvers. Don't hand-roll the chain — wrap them
(see `_resolve_property_currency` in `data_migration/loaders/pricing.py`).

### FK rewrite + hard-delete merge

The `_meta.related_objects` walk, always inside `transaction.atomic()`,
skipping `rel.many_to_many` (the through-model FK is rewritten separately).
References: `accounts.Contact.merge`, `reservations.Guest.merge`,
`merge_country`.

### Synthesised rows must not leak into public APIs

`BookingLoader` synthesises Quotation/QuotationLine rows with `legacy_id`
prefixed `booking-` (to satisfy the PROTECT FK chain). Any viewset surfacing
those models must `.exclude(legacy_id__startswith="booking-")` in
`get_queryset()` — see `QuotationViewSet`.

### Reference numbers — `db_default` sequence, not a `save()` override

Customer-facing `reference` fields (Enquiry / Payment / Refund /
SecurityDeposit) are allocated by the **database**:
`db_default=reference_db_default(...)` (`core/refs.py`) plus a Postgres
sequence created inline in the app's migration. Never a `save()` / `pre_save`
allocator — `bulk_create` skips both, leaving blank references that collide on
the unique constraint (BUG-007). An explicit value still wins (loaders
preserve legacy refs). Full detail — `RETURNING` behaviour, `setval` sync,
the Quotation/Booking `number` mechanism — in the `core/refs.py` docstring.

### State-mutating services accept `idempotency_key`

Services that create rows from external triggers (webhook, scheduled job,
operator submit) take `idempotency_key: str | None` and return the original
row on a repeat call; `None` means "not requested" (internal callers stay
ceremony-free). Helpers in `core/idempotency.py` (`find_by_meta_key` on a
*scoped* queryset, `stamp_meta`). Prefer a natural key when one exists — a
Booking is uniquely tied to its QuotationLine, so
`BookingService.create_from_quotation_line` checks the FK first. References:
`RefundService.request` / `execute`.

### Service-layer permission checks

State-mutating services take an `actor` kwarg and call
`actor_has_perm(actor, perm)` (`core.api.permissions`) for every transition;
`actor=None` is the documented system-caller sentinel, granted
unconditionally. Reference: `payments/services/refund.py`.

### Booking creation must create the LEAD `BookingGuest`

`Booking.guest` is a denormalised pointer to the LEAD `BookingGuest` row; the
`BookingGuest` table is the source of truth. Any path creating a `Booking`
must create the matching `BookingGuest(role=LEAD)` row inside the same
`transaction.atomic`. Deleting a LEAD while its booking exists raises
`LeadGuestProtectedError`; to swap LEAD, demote the old one to `CO_TRAVELLER`
and create the new LEAD atomically. References:
`BookingService.create_from_quotation_line`, `BookingLoader._process_row`,
`reservations.factories.make_occupying_booking`.

### Booking money adjustments are charge lines, not rental-figure edits

There is no `rental_price` override action (GAP-016, dropped). Adjust a
booking's money with a signed `BookingChargeItem` (e.g. "Negotiated rate
adjustment −400.00") — the label records the *why* a silent edit never could,
and the write fires `booking_total_changed`, which resyncs the unsettled
deposit/balance schedule (`PaymentScheduler.resync_for_booking`) and any
still-pre-charge security deposit (`SecurityDepositService.resize_for_booking`)
in the same transaction. The `modify_dates`/`modify_guests` re-pricing endpoints
ride the same signal. Reach for a true rental-figure override only if ops hits a
case the charge line can't express.

### AuditLog registration is part of model definition

Any PII- or money-bearing model (and any model whose docs claim an audit
trail) must be registered via `core.audit.track(Model, fields=[...],
sensitive=[...])` in its app's `AppConfig.ready()`. Track lifecycle, PII, and
money columns; skip chatty timestamps and free-form JSON blobs.
`core/tests/test_audit_registry.py` pins the registered set — update
`EXPECTED_TRACKED_MODELS` in the same commit when deregistering.

The trail rides `pre_save` / `post_delete`, so **bulk writes bypass it
silently**: `queryset.update()`, `bulk_create()`, `bulk_update()` and
`queryset.delete()` fire no signals. A bulk write to a *tracked* model must
either go through a `.save()` loop or write an explicit audit row. The merge
FK rewrites (`Contact.merge` / `Guest.merge`) use `.update()` by design and
summarise what moved onto the deletion row via `core.audit.record_merge`
(destination pk + per-relation counts, FG-016) rather than auditing each row.
If bulk paths on tracked models ever proliferate, the structural fix is
trigger-based capture (`django-pghistory`), not more signal plumbing — don't
build that now.

### Structured logging — `structlog`, event-style

Full guide: `core/logging/README.md`. Must-knows:

- `logger = structlog.get_logger(__name__)` — never `logging.getLogger`
  (ruff TID251 fails the build on it).
- Events are dotted lowercase `domain.action` with structured kwargs
  (`logger.info("booking.created", booking_id=…)`); money as `str(Decimal)`.
- Fallible operations get the triple via
  `core.logging.operations.log_operation` (times the block, emits
  `.succeeded`/`.failed`, re-raises); facts and deliberate skips get a single
  past-tense event. Don't wrap Celery tasks — django-structlog covers them.
- Reserved keys, never as kwargs: `message`, `level`, `status`, `request_id`,
  `user_id`, `correlation_id`, `service`, `env`, `release`.
- Canonical field names: `<entity>_id` pks (`booking_id`, `property_id`, …),
  `amount` = `str(Decimal)`, `currency` = ISO code, `reason` = short code;
  `duration_ms` is reserved for the triple.
- PII never lands in logs — `redact_sensitive` is a backstop, not a licence.

### Viewset querysets declare their FK reads

Every `get_queryset()` must `select_related()` / `prefetch_related()` whatever
the serializer walks — a bare `Model.objects.all()` is a bug even while FKs
serialize as PKs (the N+1 lurks for the first nested field). Pin at least one
list endpoint per app with `core.tests.assert_max_queries`. Annotations that
join a **multi-valued** relation must be gated by `self.action` and coalesced
to a real zero — an ungated one leaks its LEFT JOIN into `StatusCountsMixin`
and the paginator COUNT. Reference: `_with_amount_paid` in
`reservations/views/booking.py` and
`test_status_counts__not_inflated_by_payment_rows`.

### Test fixtures — `get_or_create` for canonical countries

Migration `properties.0009` pre-seeds 249 ISO-3166 countries. Fixtures must
use `Country.objects.get_or_create(iso2=…, defaults=…)` — never `.create`,
which violates the iso2 unique constraint against the seed.

### Realistic test data — `factory-boy` factories + `seed_dev`

Each app owns a `factories.py`; pytest fixtures and `seed_dev` both compose
the same builders. `seed_dev` is **additive** (never truncates), drives the
real service layer, and is guarded by `settings.SEED_DEV_ALLOWED`. New
factories: fold the per-process `RUN_TOKEN` (`core/factories.py`) into unique
fields, and use `django_get_or_create` for migration-seeded models. Full
reference: `seeding/README.md`.

### Validate data-migration changes via `reconcile_legacy`

After changes to loaders or legacy-importable models, run
`./manage.py reconcile_legacy` and check gaps against the documented expected
losses in `data_migration/CUTOVER.md`. Unexplained gaps are a blocker.

### Loader-transform tests prefer hand-rolled dict fixtures

The transform layer is pure (legacy dict → kwargs); test it with dict
fixtures, not the legacy DB. Mark `@pytest.mark.django_db` only when the test
exercises the Postgres schema. Style reference:
`data_migration/tests/test_country_loader.py`.

### API versioning

v1 is mutable while the in-house SPA is the only consumer — breaking changes
need a commit-message note and a same-window frontend PR. Fork `/api/v2/` only
when the API gains a second consumer we don't control.

### List / detail / write serializer split

Separate serializers when read/write shapes or list/detail depth differ;
a single serializer only when they're identical. Reference:
`reservations/views/booking.py`.

## Principles

Project-wide principles (TDD, off-the-shelf over bespoke, KISS, no soft
delete) live in the root `CLAUDE.md`. Backend-specific structure:

1. Layered architecture.

   **Vertical** (within an app, enforced by directory shape
   `<app>/{models,services,views,tests}/`): DRF handles (de)serialization
   only; ALL business logic lives in the service layer, never in views.

   **Horizontal** (which app may import which), enforced by `import-linter`
   (`uv run lint-imports`, in pre-commit + CI):

   - **`core` is the foundation.** Cross-cutting primitives only; `core`
     imports **no** domain app, ever. This is the crown-jewel invariant.
   - **Spine points down** — a layer may import those below it:

     ```
     comms > payments > reservations > owners > pricing > properties > integrations > accounts
     ```

     The few sanctioned back-edges are commented `ignore_imports` lines in
     `pyproject.toml`; a genuinely new seam gets added there with a one-line
     justification, never silently. `seeding` and `data_migration` sit outside
     the layers contract but still obey the `core` rule.

2. One **aggregate** per file in `<app>/models/*`: a root model and its
   dependent rows (children, events, through models) live together; unrelated
   roots get their own module. (The codebase already follows this — e.g.
   `reservations/models/booking.py` holds Booking + its dependents — so the rule
   describes reality rather than the older "one model per file" wording it
   replaces; do not churn files to split aggregates apart.)
