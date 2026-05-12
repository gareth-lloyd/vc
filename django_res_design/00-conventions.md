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

| Model kind | Base |
|---|---|
| Lookup tables staff curate (`Country`, `Region`, `Currency`, `Feature`, `Collection`, `PropertyCategory`) | `TimestampedModel` + `is_active` bool |
| All user-editable domain models | `AuditedModel` |
| Append-only audit / event tables (`BookingEvent`, `PaymentEvent`, `EnquiryEvent`, `WebhookDelivery`, `FxRate`, `EmailLog`, `SyncRun`, `SyncIssue`) | `TimestampedModel` only (never deleted) |
| Pure-data junctions with no user lifecycle (`CollectionMembership`) | `TimestampedModel` |
| Fixed enumerations (Status, Channel, Role, Kind) | **No table** — `models.TextChoices` |

## Lifecycle, not soft delete

Opaque hidden rows (`deleted_at IS NOT NULL`, hidden by a default manager) are not allowed. Every model's lifecycle is expressed via an explicit, queryable, visible signal. Pick the right pattern per concern:

| Need | Pattern |
|---|---|
| Lifecycle states (draft / active / archived / cancelled / expired / declined / anonymized) | `status` TextChoices on the model; add a dated timestamp for state entry (`archived_at`, `cancelled_at`, `settled_at`) when audit demands it |
| On/off toggle for lookups and catalogues | `is_active` BooleanField; apply an `is_active=True` default manager scope **only when reads require it** (most lookup tables don't — read-time filtering is fine and avoids the surprise of a hidden manager) |
| Owned child rows | hard delete via CASCADE from the parent |
| Cross-aggregate references | `on_delete=PROTECT` — the FK forbids deleting a row that has downstream usage |
| Audit history of state transitions | append-only event tables (`BookingEvent`, `PaymentEvent`, `EnquiryEvent`) — never deleted |
| Audit history of sensitive-config field edits | per-model `AuditLog` row written by a `pre_save` signal (see below) |
| Personal-data removal under GDPR | **anonymization-in-place**: an explicit service method (`Contact.anonymize()`, `Guest.anonymize()`) overwrites PII fields with sentinels (`"[REDACTED]"`, `"redacted-{id}@anonymized.local"`, empty strings) and sets `status=ANONYMIZED`. The row stays so FK integrity on historical bookings is preserved; the fact of anonymization is **visible**, not hidden |
| Merging duplicate records | explicit service method (`Contact.merge(target)`, `Guest.merge(target)`) — rewrites every FK pointing at `self` to point at `target`, writes one `AuditLog` row per rewrite, then **hard-deletes** `self`. No tombstone row, no `merged_into` self-FK |
| "Wrong record, undo" with no downstream rows | hard delete — the `PROTECT` FKs upstream already gate this |

If you reach for "hide this row from default queries", stop and name the lifecycle state instead.

### `AuditLog`

A single per-app table that captures sensitive-field edits as an append-only diff stream. Used in particular by `properties.PropertyFinance` and its children (`Commission`, `TaxPolicy`, `BankAccount`, `PaymentSchedule`, `SecurityDepositPolicy`) and by `accounts.Contact` for PII-relevant fields.

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
