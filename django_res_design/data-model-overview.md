# Data Model Overview

A descriptive map of the backend data model in `django_res/`: the
fundamental building blocks, how they fit together, and the cross-cutting
patterns that recur across apps.

This is orientation, not a spec — keep it in sync with the code as the
model evolves. Known issues and planned changes live in
[`todo/`](todo/INDEX.md); this document only describes what exists.

---

## 1. Apps and their domains

| App | Domain | Anchor model(s) |
|---|---|---|
| `accounts` | Auth users, business contacts (owners/agents/managers), sessions, RBAC | `User`, `Contact` |
| `properties` | The villa catalogue + inheritable per-property settings/finance + geography | `Property` |
| `pricing` | Three-tier price model + surcharges/discounts + FX | `RatePlan` → `RateCard` → `RateRule` |
| `reservations` | Enquiry → Quotation → Booking lifecycle, plus guests, terms, holds, concierge | `Booking`, `Guest`, `Quotation` |
| `payments` | Unified payment ledger + events + refunds + webhooks + security deposit | `Payment` |
| `comms` | Email sending (SMTP profiles, templates, append-only log) | `EmailLog` |
| `integrations` | Generic sync metadata, Zoho OAuth, sync run audit | `SyncRecord` |
| `core` | Shared base classes, audit registry, idempotency, reference generation | `TimestampedModel`, `AuditedModel`, `AuditLog`, `IdempotencyRecord` |

## 2. Anchor models

Five models carry the weight of the system:

- **`Property`** — focal point for pricing, settings, finance, rooms, images,
  features, and contact assignments. Has the largest "satellite cluster":
  `PropertySettings`, `PropertyFinance`, `PropertyCapacity`, `Room`,
  `PropertyImage`, `PropertyDescription`, `PropertyLocation`, plus M2M to
  `Contact` via `PropertyContactAssignment`.
- **`Booking`** — central to reservations. Has its own satellite cluster:
  `BookingEvent`, `BookingNote`, `BookingHold`, `BookingConciergeItem`, and a
  1:N to `Payment`.
- **`Guest`** — unified customer across Enquiry → Quotation → Booking. Has an
  optional `OneToOne` to `User`.
- **`Contact`** — owner/manager/agent counterpart to Guest. Also has an
  optional `OneToOne` to `User`. PII-anonymizable.
- **`Payment`** — single-table polymorphic ledger keyed on a `purpose` enum
  (`DEPOSIT` | `BALANCE` | `SECURITY_DEPOSIT` | `CONCIERGE` | `REFUND` |
  `ADJUSTMENT`).

Every other model is best understood as either a satellite of one of these
anchors, a lookup/config row, or a cross-cutting audit/sync record.

## 3. Relationships (high-level)

```
Property ─1:N→ RatePlan ─1:N→ RateCard ─1:N→ RateRule
         ─1:1→ PropertySettings, PropertyFinance, PropertyCapacity
         ─1:N→ Room, PropertyImage, PropertyDescription, PropertyLocation
         ─M:M→ Contact (via PropertyContactAssignment)
         ─M:M→ Feature, Collection

Enquiry ─1:N→ Quotation ─1:N→ QuotationLine ─1:N→ Booking
Guest   ─1:N→ Quotation, Booking            (also User OneToOne)
Contact ─1:N→ Quotation.agent, Booking.agent (also User OneToOne)

Booking ─1:N→ Payment, BookingHold, BookingEvent, BookingNote, BookingConciergeItem
Payment ─1:N→ PaymentEvent, PaymentLine, Refund, WebhookDelivery

(any model) ─1:N→ SyncRecord  (GenericFK via ContentType + object_id)
EmailLog    ─N:1→ SmtpProfile, TermsVersion (loosely, via correlation key)
```

## 4. Cross-cutting patterns

### Base classes (`core/models/base.py`)
- `TimestampedModel` — `created_at` (`auto_now_add`), `updated_at` (`auto_now`).
- `AuditedModel(TimestampedModel)` — adds `created_by` / `updated_by` FKs
  (`PROTECT`, `editable=False`).

Most domain models extend `AuditedModel`. A handful of lookup tables
(`NearbyPlaceType`, `RoomBeds`, `FeatureCategory`, `SyncRecord`) extend only
`TimestampedModel` or neither.

### Legacy migration
Every importable domain model carries a `legacy_id` field
(`CharField`, `db_index=True`). Loaders in `django_res/data_migration/` use
`update_or_create(legacy_id=…)` to stay idempotent. `legacy_id` is metadata,
never the primary key. Sentinel fallbacks (`unknown_country`,
`unknown_region`) absorb unresolvable FKs.

### State machines
Each lifecycle model (`Booking`, `Payment`, `Quotation`, …) has:
- a `status` `CharField(choices=…)` with an explicit enum
- per-transition methods on the model (e.g. `Booking.submit_for_approval()`)
- transitions wrapped in `transaction.atomic()`, writing an event row and
  emitting a signal
- `CheckConstraint`s enforcing date/status coherence

### Inheritable settings
Two parallel patterns, one for settings, one for finance. Every inheritable
field on the property is nullable; `None` means "fall back to group":

- `PropertySettings` / `GroupSettings` — resolution via
  `PropertySettings.effective(attr)`.
- `PropertyFinance` / `GroupFinance` — resolution via
  `_FinanceFieldMixin.effective(field)`.

Both resolvers share the shape:
```python
def effective(self, attr):
    own = getattr(self, attr)
    if own is not None and own != "":
        return own
    return getattr(self.property.group.<settings|finance>, attr)
```

`PropertyFinance` then exposes grouped resolvers like
`effective_commission()`, `effective_tax_policy()`,
`effective_payment_schedule()`, `effective_security_deposit_policy()`,
`effective_bank_account()`.

### Idempotency
- `IdempotencyRecord` table — `(user, path, key)` unique together — used at
  the HTTP boundary.
- `meta["idempotency_key"]` stamped on state-mutating service calls
  (Payment, Refund, Booking creation).
- `EmailLog` uses a SHA-256 content hash of
  `(template_key, sorted(to), correlation)` to deduplicate sends.

### Audit and permissions
- `AuditLog` registry — each app's `AppConfig.ready()` calls
  `track(Model, fields=[...], sensitive=[...])` to register fields whose
  changes should be logged.
- Service layer calls `actor_has_perm(actor, perm)`; `actor=None` means
  *system / tests*.

### References
Anchor models carry a human-readable, `unique` `reference` `CharField`, allocated
by the **database** (BUG-007), not Python:

- **Enquiry / Payment / Refund / SecurityDeposit** — the column's `db_default`
  (`core.refs.reference_db_default`) draws from a per-series Postgres sequence
  and stamps `{prefix}-{year}-{nextval}` on *every* insert path (`save()`,
  `bulk_create`, raw SQL). No `save()` override; an explicit value (legacy
  loaders) still wins.
- **Quotation / Booking** — a shared sequence-backed `number` (`QVC{n}` /
  carried-forward `VC{n}`, legacy parity). `generate_reference` survives only as
  Booking's interim fallback for a numberless quotation.

The earlier `save()`-via-`generate_reference()` scheme was replaced because
`bulk_create` bypasses `save()` (and signals), leaving a blank `reference` that
collided on the unique constraint. See `django_res/CLAUDE.md` §"Reference
numbers".

### Soft delete
None. Lifecycle is expressed via `status` + `is_active` + `archived_at`, or a
hard delete paired with an `AuditLog` trail:
- `Contact` and `Guest` use `status` + `anonymized_at` + `anonymize()` for PII
  erasure.
- Hard deletes are paired with `AuditLog` rows (e.g. `Contact.merge`).

### ID strategy
Auto-increment bigint PKs throughout. No UUIDs except in tests.
`SyncRecord.object_id` is `PositiveBigIntegerField` to match.

## 5. Payment ledger — single-table polymorphism

`Payment` is one table partitioned by `purpose`
(`DEPOSIT` | `BALANCE` | `SECURITY_DEPOSIT` | `CONCIERGE` | `REFUND` |
`ADJUSTMENT`), with indexes on `(booking, purpose)` and a uniqueness rule on
the active payment per purpose for the DEPOSIT/BALANCE subset.

A separate `SecurityDeposit` model also exists, so security-deposit money
flows are currently represented twice — once as a `Payment` row with
`purpose=SECURITY_DEPOSIT`, once as a `SecurityDeposit` row. Whether
`Payment` should be a generic ledger or the customer-facing money request
(with `SECURITY_DEPOSIT` living only in `SecurityDeposit`) is an open
decision — see [Q-016](todo/q-016-payment-ledger-vs-dedicated-models.md).
