# 00 — Cross-cutting Conventions

Shared rules that every app obeys. Put the abstract bases in a `core` app (no models of its own; just `models/base.py`, `middleware.py`, `signals.py`).

## Abstract base models

A three-link chain. Concrete models pick the level they need.

```
TimestampedModel       (auto timestamps)
  ↑ AuditedModel       (+ created_by / updated_by)
    ↑ SoftDeleteModel  (+ deleted_at / deleted_by + filtering manager)
```

### `TimestampedModel`
- `created_at` — `DateTimeField(auto_now_add=True, db_index=True)`
- `updated_at` — `DateTimeField(auto_now=True)`

### `AuditedModel(TimestampedModel)`
- `created_by` — `ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=PROTECT, related_name='+')`
- `updated_by` — same shape

### `SoftDeleteModel(AuditedModel)`
- `deleted_at` — `DateTimeField(null=True, blank=True, db_index=True)`
- `deleted_by` — `ForeignKey(User, null=True, blank=True, on_delete=PROTECT, related_name='+')`
- `objects = SoftDeleteManager()` — filters `deleted_at__isnull=True` by default
- `all_objects = models.Manager()` — full unfiltered access for admin/recovery
- `delete()` — overridden to set timestamps; `hard_delete()` exposes real DB delete

## Which base to use

| Model kind | Base |
|---|---|
| Lookup tables staff curate (`Country`, `Region`, `Currency`, `Feature`, `Collection`, `PropertyCategory`) | `TimestampedModel` + `is_active` bool |
| All user-editable domain models | `SoftDeleteModel` |
| Append-only audit / event tables (`BookingEvent`, `PaymentEvent`, `WebhookDelivery`, `FxRate`) | `TimestampedModel` only (never deleted) |
| Pure-data junctions with no user lifecycle (`CollectionMembership`) | `TimestampedModel` |
| Fixed enumerations (Status, Channel, Role, Kind) | **No table** — `models.TextChoices` |

## Audit middleware

Populate `created_by`/`updated_by`/`deleted_by` automatically. Threadlocal pattern:

- `core.middleware.AuditMiddleware` — stores `request.user` on a thread-local at request start; clears it at response.
- `core.signals` — `pre_save` handler reads the thread-local, populates `created_by` (if pk is None) and `updated_by`. `pre_delete` handler (or override in `SoftDeleteModel.delete()`) populates `deleted_by`.
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

## Soft-delete and cascade

When a parent has soft-delete and a child has a FK:
- `on_delete=PROTECT` is the default — don't let admins delete a property that has bookings.
- `on_delete=CASCADE` only for true ownership relationships (Property → PropertyLocation OneToOne, Quotation → QuotationLine, Payment → PaymentEvent).
- Soft-delete is not propagated automatically; if a property is archived, bookings remain queryable. The manager filtering means it disappears from default UIs without orphaning history.

## Migrations hygiene

- One migration per logical change; never edit applied migrations.
- For Postgres-specific constraints (`EXCLUDE`, custom indexes), use `RunSQL` with a reverse SQL.
- Use `Meta.constraints` for `UniqueConstraint` and `CheckConstraint` — Django manages them.
