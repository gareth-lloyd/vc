# 00 — Cross-cutting Conventions

Shared rules that every app obeys. Put the abstract bases in a `core` app (no models of its own; just `models/base.py`, `middleware.py`, `signals.py`).

## Abstract base models

A two-link chain. Concrete models pick the level they need. **There is no `SoftDeleteModel` in this codebase** — see "Lifecycle, not soft delete" below.

```
TimestampedModel       (auto timestamps)
  ↑ AuditedModel       (+ created_by / updated_by)
```

### `TimestampedModel`

- `created_at` — `DateTimeField(auto_now_add=True, db_index=True)`
- `updated_at` — `DateTimeField(auto_now=True)`

### `AuditedModel(TimestampedModel)`

- `created_by` — `ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=PROTECT, related_name='+')`
- `updated_by` — same shape

## Which base to use

| Model kind                                                                                                                                         | Base                                    |
| -------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| Lookup tables staff curate (`Country`, `Region`, `Currency`, `Feature`, `Collection`, `PropertyCategory`)                                          | `TimestampedModel` + `is_active` bool   |
| All user-editable domain models                                                                                                                    | `AuditedModel`                          |
| Append-only audit / event tables (`BookingEvent`, `PaymentEvent`, `EnquiryEvent`, `WebhookDelivery`, `FxRate`, `EmailLog`, `SyncRun`, `SyncIssue`) | `TimestampedModel` only (never deleted) |
| Pure-data junctions with no user lifecycle (`CollectionMembership`)                                                                                | `TimestampedModel`                      |
| Fixed enumerations (Status, Channel, Role, Kind)                                                                                                   | **No table** — `models.TextChoices`     |

## Lifecycle, not soft delete

Opaque hidden rows (`deleted_at IS NOT NULL`, hidden by a default manager) are not allowed. Every model's lifecycle is expressed via an explicit, queryable, visible signal. Pick the right pattern per concern:

| Need                                                                                       | Pattern                                                                                                                                                                                                                                                                                                                                                            |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Lifecycle states (draft / active / archived / cancelled / expired / declined / anonymized) | `status` TextChoices on the model; add a dated timestamp for state entry (`archived_at`, `cancelled_at`, `settled_at`) when audit demands it                                                                                                                                                                                                                       |
| On/off toggle for lookups and catalogues                                                   | `is_active` BooleanField; apply an `is_active=True` default manager scope **only when reads require it** (most lookup tables don't — read-time filtering is fine and avoids the surprise of a hidden manager)                                                                                                                                                      |
| Owned child rows                                                                           | hard delete via CASCADE from the parent                                                                                                                                                                                                                                                                                                                            |
| Cross-aggregate references                                                                 | `on_delete=PROTECT` — the FK forbids deleting a row that has downstream usage                                                                                                                                                                                                                                                                                      |
| Audit history of state transitions                                                         | append-only event tables (`BookingEvent`, `PaymentEvent`, `EnquiryEvent`) — never deleted                                                                                                                                                                                                                                                                          |
| Audit history of sensitive-config field edits                                              | per-model `AuditLog` row written by a `pre_save` signal (see below)                                                                                                                                                                                                                                                                                                |
| Personal-data removal under GDPR                                                           | **anonymization-in-place**: an explicit service method (`Contact.anonymize()`, `Guest.anonymize()`) overwrites PII fields with sentinels (`"[REDACTED]"`, empty strings) and sets `status=ANONYMIZED`. The row stays so FK integrity on historical bookings is preserved; the fact of anonymization is **visible**, not hidden. Email differs by model: `Contact` replaces `ContactEmail.email` with `"redacted-{id}@anonymized.local"` (child-table column is `NOT NULL`), whereas the now-nullable `Guest.email` is set to `NULL` (no synthetic) — see `people-model-cleanup.md` |
| Merging duplicate records                                                                  | explicit service method (`Contact.merge(target)`, `Guest.merge(target)`) — rewrites every FK pointing at `self` to point at `target`, writes one `AuditLog` row per rewrite, then **hard-deletes** `self`. No tombstone row, no `merged_into` self-FK                                                                                                              |
| "Wrong record, undo" with no downstream rows                                               | hard delete — the `PROTECT` FKs upstream already gate this                                                                                                                                                                                                                                                                                                         |

If you reach for "hide this row from default queries", stop and name the lifecycle state instead.

### `AuditLog`

A single table with a generic foreign key that captures sensitive-field edits as an append-only diff stream. Used in particular by `properties.PropertyFinance` and its children (`Commission`, `TaxPolicy`, `BankAccount`, `PaymentSchedule`, `SecurityDepositPolicy`) and by `accounts.Contact` for PII-relevant fields.

- `id` — UUID
- `content_type` — FK `ContentType` (the model whose row changed)
- `object_id` — string PK of the row
- `actor` — FK User SET_NULL, null=True
- `field_diffs` — JSONField — `{field_name: [old_value, new_value], ...}`; redacted for fields tagged sensitive (e.g. `iban`, `account_number` write a `"[REDACTED]"` sentinel rather than the cleartext value)
- `correlation_id` — UUID, groups related changes in one operation
- `created_at` — DateTimeField(auto_now_add)

Indexes: `(content_type, object_id, created_at)`, `(actor, created_at)`.

The signal handler reads `pre_save` for any model that registers itself with `core.audit.track(Commission, fields=[...])`. Models don't grow a per-model history table; they emit diffs into the shared `AuditLog` keyed by content type.

## Audit middleware

Populate `created_by`/`updated_by` automatically. Threadlocal pattern:

- `core.middleware.AuditMiddleware` — stores `request.user` on a thread-local at request start; clears it at response.
- `core.signals` — `pre_save` handler reads the thread-local, populates `created_by` (if pk is None) and `updated_by`. The same handler emits an `AuditLog` row for any model registered via `core.audit.track(...)`.
- For management commands / Celery tasks, expose a context manager: `with current_user_as(user): ...`.

## Idempotency

The API contract (`product-design/04-rest-api-surface.md` §1) honours `Idempotency-Key` on every `POST` action endpoint and every payment-creating endpoint. Implementation is generic — there is no per-model `idempotency_key` column. See reconciliation issue #39.

### `core.IdempotencyRecord`

A single table records (key, user, endpoint, body-hash, response). Replaying the same key returns the cached response; replaying with a different body returns `409`.

- `key` — `CharField(max_length=128)` — client-supplied `Idempotency-Key` header value
- `user` — `ForeignKey(User, on_delete=PROTECT)` — scopes the key per-caller; anonymous endpoints (public quote, public enquiry) scope by `(ip, user_agent_hash)` written into the same column via a synthetic-user pattern, or skip the key entirely
- `method` — `CharField(max_length=8)` — `POST` in practice; recorded for clarity
- `path` — `CharField(max_length=512)` — request path; included in the dedupe key so the same `Idempotency-Key` value used against two different endpoints does not collide
- `request_hash` — `CharField(max_length=64)` — SHA-256 of the canonical-JSON request body; replaying the same key with a different body is a client bug → respond `409 Conflict`
- `response_status` — `PositiveSmallIntegerField`
- `response_body` — `JSONField`  # cached response payload
- `response_headers` — `JSONField(default=dict)` — content-type + any `Location` header from the original response
- `created_at` — `DateTimeField(auto_now_add=True, db_index=True)`
- `expires_at` — `DateTimeField(db_index=True)` — `created_at + 24h` default; nightly Celery beat task (`cleanup_idempotency_records`) deletes expired rows

Constraint: `UniqueConstraint(user, path, key, name="unique_idempotency_key_per_user_path")`.

### `core.middleware.IdempotencyMiddleware`

DRF middleware (or DRF mixin if we want per-view opt-in) that intercepts the request before the view runs:

1. If the request method is not `POST`, pass through.
2. If no `Idempotency-Key` header is present:
   - On endpoints flagged as **requiring** the header (payment creation, booking creation, refund creation — anything that moves money or commits significant state), respond `400 Bad Request` with `code=idempotency_key_required`.
   - On endpoints flagged as **optional**, pass through.
3. With a header present, look up the `(user, path, key)` tuple.
   - **Hit** with matching `request_hash`: short-circuit the view; return the cached response. Records the replay in `AuditLog`.
   - **Hit** with mismatched `request_hash`: return `409 Conflict` with `code=idempotency_key_mismatch`.
   - **Miss**: acquire an advisory lock on `(user, path, key)` (Postgres `pg_advisory_xact_lock`) inside the view's `transaction.atomic`; on commit, write the `IdempotencyRecord` row with the captured response.

The middleware is endpoint-policy-driven: each view declares `idempotency_required = True | False` (default `True` for payment + booking + refund creation, `False` elsewhere). The off-the-shelf `django-idempotency-key` package solves a subset of this but doesn't model the hash mismatch as `409` cleanly, so we ship our own thin layer over `IdempotencyRecord`. Revisit if a maintained library catches up.

### Why generic, not per-model

The legacy backend carried `idempotency_key` on `Payment`, `Refund`, and `SecurityDeposit`. Those columns are removed in favour of `IdempotencyRecord`: the dedupe lives at the API boundary, not in the model, and a single mechanism covers every unsafe POST — not just the money-moving ones.

## Storage backends

File uploads (property images, document attachments, exports, generated PDFs) land on S3 via [`django-storages`](https://django-storages.readthedocs.io/) with `boto3`. **No local-disk storage in any environment** — local dev points at a MinIO container (already in `docker-compose.yml`) configured with the same `boto3` client. See reconciliation issue #40.

### Settings

- `DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"` (or `S3StaticStorage` for static assets).
- Bucket per environment: `villacollective-dev`, `-staging`, `-prod`.
- Key layout: `{app}/{model}/%Y/%m/{uuid}{ext}` — e.g. `properties/propertyimage/2026/05/2c3a…b9f1.jpg`. The `uuid` keeps keys non-guessable; the legacy `properties/%Y/%m/` shape on `PropertyImage.image` is preserved by configuring `upload_to` on the field — only the storage backend changes.
- Bucket policy denies public reads; every download is a signed `GET` URL generated by the API.

### Two-step signed upload

The API contract is in `product-design/04-rest-api-surface.md` §1 ("Two-step: `POST /uploads:sign` returns a signed S3 URL the client PUTs to. Then the client `POST`s the resulting key to the consuming resource."). Backend support:

- `core.UploadTicket(TimestampedModel)` — minimal row recording `(user, path, key, content_type, max_bytes, expires_at, consumed_at)`. Issued by `POST /uploads:sign`; consumed by `POST /properties/{id}/images` and other attach endpoints; expires after 1 hour if unused (Celery beat task `expire_upload_tickets`).
- The attach endpoint validates the key against `UploadTicket`, calls `boto3.head_object` to confirm the file exists, and **only then** writes the consuming model row (`PropertyImage`, etc.). The model's `image` field stores the key relative to the bucket, exactly as `django-storages` expects.
- Small files (avatar, docs < 5 MB) may still POST directly to `POST /uploads`; the view streams the body into S3 server-side via `boto3` and returns the same `{key}` shape as the two-step flow. Same `UploadTicket` audit trail.

### Why S3, not local

The legacy `ImageField(upload_to="properties/%Y/%m/")` shape is preserved at the field level; only the storage backend changes. Two-step signed URLs avoid streaming uploads through Django (saves CPU, sidesteps the Django request-body size limit, decouples the upload from API response latency). Local-disk was never going to scale past one app server.

## Naming

- Models: singular PascalCase (`Property`, not `Properties`).
- Fields: lower_snake_case.
- Foreign keys: name reflects the relationship purpose, not the target type (`owner_contact` not `contact_id`).
- Booleans: positive form, no `is_` prefix on names that have a clearer verb (`active` over `is_active` is fine; we'll standardise on `is_active`/`is_primary` for consistency with the legacy field shape, then evolve).
- Timestamps: `*_at` (`expires_at`, `settled_at`).
- Enum field name = singular noun (`status`, `kind`, `purpose`, `channel`).
- `legacy_id` — every domain model gets a nullable, indexed `legacy_id: CharField(max_length=64, null=True, blank=True)` for future reconciliation, even though no migration is planned.

## Money & currency

- **No `django-money`**. Use `DecimalField(max_digits=12, decimal_places=2)` for amounts and a `Currency` FK on every monetary model.
- Currency: `pricing.Currency` (code char(3), symbol, decimal_places, is_active). ISO 4217.
- FX: `pricing.FxRate` is append-only; `pricing.services.FxConverter.convert(amount, from_ccy, to_ccy, as_of=None)` picks the latest rate ≤ `as_of`. Never store a converted amount as the source of truth; convert at read time.
- Snapshots: when a price is "locked" (on `Booking.pricing_snapshot`), persist the JSON breakdown — never re-derive.

## Enums via `TextChoices`

Use `TextChoices` for any closed, app-controlled set. String values (not integers) for queryability and migrations. Example:

```
class BookingStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING_OWNER_APPROVAL = "pending_owner_approval", "Pending owner approval"
    ...
```

Lookups become `is_active` lookup tables only when:

- the set is staff-curated (e.g. `Country`, `Feature`), or
- the row carries real metadata (e.g. `Country.tax_rate`).

## Postgres requirements

- Postgres 14+.
- `btree_gist` extension enabled (for `daterange` `EXCLUDE` constraints on availability & rate rules). Add via a `RunSQL` migration in `core/migrations/0001_extensions.py`.
- `citext` extension for case-insensitive email indices (Guest.email, ContactEmail.email).

## File layout per app

```
appname/
├── __init__.py
├── apps.py
├── enums.py                # all TextChoices for the app
├── models/                 # package, not module — keeps clusters scannable
│   ├── __init__.py         # re-exports
│   ├── base.py             # only when app has its own bases
│   └── *.py                # one file per domain cluster
├── services.py             # stateless service classes / functions
├── signals.py              # signal handlers (registered in apps.py ready())
├── managers.py             # custom QuerySets/Managers
├── admin.py
├── migrations/
└── tests/
```

## Validation strategy

- DB constraints first (FK, unique, exclude, check) — fail loud, fail at commit.
- Model `clean()` for cross-field validation; called in admin and via `full_clean()` in services.
- Views/forms add presentation-layer validation only.
- Never put business invariants in JS/template land.

## FK on_delete defaults

- `on_delete=PROTECT` is the default — never let a delete cascade silently across aggregates.
- `on_delete=CASCADE` only for true ownership relationships within one aggregate (Property → PropertyLocation OneToOne, Quotation → QuotationLine, PropertyFinance → Commission).
- "Archive" the parent (set `status=ARCHIVED`) when you want it out of the default list without orphaning history; children stay live and queryable. Lifecycle transitions never produce hidden rows.

## Migrations hygiene

- One migration per logical change; never edit applied migrations.
- For Postgres-specific constraints (`EXCLUDE`, custom indexes), use `RunSQL` with a reverse SQL.
- Use `Meta.constraints` for `UniqueConstraint` and `CheckConstraint` — Django manages them.

## Background jobs (Celery beat)

The legacy `SchedullerJob` class was checked in but `[DISABLED]` in production (`workflows/12-automation/scheduler-jobs.md`). Every recurring job below is enabled from day one in the Django port; each declares its idempotency strategy so duplicate runs are safe.

| Task | App | Schedule | Purpose |
|---|---|---|---|
| `expire_holds` | `reservations` | every 1 min | Sets `released_at = now()` on `BookingHold`s past `expires_at`; emits `hold_expired` signal. See `06-availability.md`. |
| `escalate_pending_owner_approvals` | `reservations` | every 1 h | Owner-approval requests pending past a configurable threshold emit `owner_approval_reminder` for `comms`. Does not auto-approve. |
| `send_payment_reminders` | `payments` | every 1 h | Per-purpose reminder logic (deposit due, balance 7-day warning, balance due, SD due). Idempotent via `EmailLog` correlation lookup (no `Payment.reminder_sent_at` column needed). |
| `process_sd_refunds` | `payments` | every 1 h | `SecurityDeposit.kind=PRE_AUTH_HOLD` → triggers `:release` on/after `release_scheduled_for`; `BT_REFUNDABLE` → opens a `Refund` row and queues `:execute`. Flagged for ops review if a damage claim is pending on the booking. |
| `expire_quotations` | `reservations` | every 15 min | DRAFT/SENT quotations past `expires_at` -> `EXPIRED` via `Quotation.expire()`. Idempotent (per-row `InvalidTransition` skip). |
| `expire_bookings` | `reservations` | hourly | AWAITING_DEPOSIT bookings whose deposit Payment `due_at` is older than `BOOKING_DEPOSIT_EXPIRY_DAYS` (default 7) -> `EXPIRED`; leftover PENDING payments expired by the payments-side `booking_transitioned` receiver. Idempotent. |
| `arm_balances` | `reservations` | daily 06:00 UTC | DEPOSIT_PAID bookings on/after `balance_due_at` -> `AWAITING_BALANCE`; runs before `send_payment_reminders` so a booking arms the morning its first reminder could fire. Idempotent. |
| `sweep_unprocessed_webhook_deliveries` | `payments` | every 10 min | Re-enqueues signature-valid `WebhookDelivery` rows >15 min old with no `processed_at` (lost enqueues / exhausted retries); rows at the retry cap logged as `stuck`. Idempotent (delivery-level processing guard). |
| `auto_check_out` | `reservations` | every 1 h | Transitions bookings from `CHECKED_IN` to `CHECKED_OUT` once their `date_to` has passed, opening the SD release path. |
| `rebuild_pricing_summary` | `pricing` | debounced via signal | Rebuilds `VillaPricingSummary` rows; not on a fixed schedule — fired by `post_save`/`post_delete` on `RateRule` / `RatePlan`. Nightly refresh of `next_available_date` runs at 03:00 local time. |
| `cleanup_orphan_images` | `properties` | weekly (Sun 04:00) | Removes `properties/%Y/%m/` files with no `PropertyImage` row pointing at them. |
| `zoho_reconciliation` | `integrations` | nightly | Compares fingerprints in `SyncRecord` to source rows; opens `SyncIssue`s for drift. |
| `cleanup_idempotency_records` | `core` | nightly (03:30) | Deletes `IdempotencyRecord` rows past `expires_at`. Idempotent (delete-where). |
| `expire_upload_tickets` | `core` | hourly | Deletes `UploadTicket` rows past `expires_at` with `consumed_at IS NULL`. |
