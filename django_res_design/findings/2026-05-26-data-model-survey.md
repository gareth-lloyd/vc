# Data Model Survey — 2026-05-26

A snapshot of the backend data model in `django_res/`: what the fundamental
building blocks are, how they fit together, and where they could be improved.

This is a *findings* document — descriptive, not prescriptive. Any of the
"could be better" items deserves its own design discussion before being
acted on.

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
  features, and contact assignments. Property has the largest "satellite
  cluster": `PropertySettings`, `PropertyFinance`, `PropertyCapacity`, `Room`,
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

Every other model in the system is best understood as either a satellite of
one of these anchors, a lookup/config row, or a cross-cutting audit/sync
record.

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

Most domain models extend `AuditedModel`. A handful (lookup tables like
`NearbyPlaceType`, `RoomBeds`, `FeatureCategory`, and `SyncRecord`) extend
only `TimestampedModel` or neither.

### Legacy migration
Every importable domain model carries a `legacy_id` field. Loaders in
`django_res/data_migration/` use `update_or_create(legacy_id=…)` to stay
idempotent. `legacy_id` is metadata, never the primary key. Sentinel
fallbacks (`unknown_country`, `unknown_region`) absorb unresolvable FKs.

### State machines
Each lifecycle model (`Booking`, `Payment`, `Quotation`, …) has:
- a `status` `CharField(choices=…)` with an explicit enum
- per-transition methods on the model (e.g. `Booking.submit_for_approval()`)
- transitions wrapped in `transaction.atomic()`, writing an event row and
  emitting a signal
- `CheckConstraint`s enforcing date/status coherence

Example — `Booking` (`reservations/models/booking.py:121–138`):
```python
CheckConstraint(
    condition=Q(cancelled_at__isnull=True) | Q(status=BookingStatus.CANCELLED.value),
    name="booking_cancelled_at_implies_cancelled_status",
)
CheckConstraint(
    condition=Q(archived_at__isnull=True) | Q(status__in=TERMINAL_BOOKING_STATUSES),
    name="booking_archived_at_requires_terminal_status",
)
```

### Inheritable settings
Two nearly identical patterns, one for settings, one for finance:

- `PropertySettings` / `GroupSettings` — every inheritable field on the
  property is nullable; `None` means "fall back to group". Resolution via
  `PropertySettings.effective(attr)` (`properties/models/settings.py:79`).
- `PropertyFinance` / `GroupFinance` — same shape, resolution via
  `_FinanceFieldMixin.effective(field)` (`properties/models/finance.py:33`).

Both `effective()` implementations are structurally identical:
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
`effective_bank_account()` (`properties/models/finance.py:192–243`).

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
Anchor models (`Booking`, `Payment`, `Quotation`) carry a human-readable
`reference` `CharField` generated in `save()` via `generate_reference()`.

### Soft delete
None. CLAUDE.md is explicit, and the code honours it:
- `Contact` and `Guest` use `status` + `anonymized_at` + `anonymize()` for PII
  erasure.
- Hard deletes are paired with `AuditLog` rows (e.g. `Contact.merge`).

### ID strategy
Auto-increment bigint PKs throughout. No UUIDs except in tests.
`SyncRecord.object_id` is `PositiveBigIntegerField` to match.

## 5. Payment ledger — single table polymorphism

Worth calling out separately because it is unusual in this codebase.

`Payment` is one table partitioned by `purpose`
(`payments/models/payment.py:39–110`):

```python
purpose = models.CharField(max_length=24, choices=PaymentPurpose.choices)
# … indexes on (booking, purpose), unique constraint on active payment per
# purpose for the non-refund/non-adjustment subset
```

A separate `SecurityDeposit` model also exists. Security-deposit money flows
end up represented twice — once as a `Payment` row with
`purpose=SECURITY_DEPOSIT`, once as a `SecurityDeposit` row. See §6.1.

---

## 6. What could be better

Each of the following is a *direction for discussion*, not a recommended
change. They're roughly ordered by how much architectural pain they cause
today.

### 6.1. Payment.purpose vs the SecurityDeposit model — pick a lane

The `purpose` enum is doing the work of a polymorphic ledger:
`DEPOSIT` | `BALANCE` | `SECURITY_DEPOSIT` | `CONCIERGE` | `REFUND` |
`ADJUSTMENT` (`payments/models/payment.py:48`). At the same time, a
dedicated `SecurityDeposit` model lives in
`payments/models/security_deposit.py`. The two representations of "money
held against damage" co-exist:

- Pro single-table: queries like "all money flows for booking X" stay
  trivial; one set of state machines and webhook handlers.
- Pro dedicated models: each purpose has a different lifecycle (security
  deposits get returned after departure, deposits don't), different fields,
  different reporting needs. A single table forces nullable fields and
  conditional check constraints.

The current hybrid has the worst of both: callers need to know both
representations exist, and which one is authoritative for a given query is
not obvious.

**Direction:** decide whether `Payment` is a *generic ledger* (in which case
`SecurityDeposit` becomes a thin view/manager over Payment rows) or
`Payment` is *the customer-facing money request* (in which case
`SECURITY_DEPOSIT` should leave the purpose enum and live entirely in
`SecurityDeposit`).

### 6.2. Two near-identical inheritance mixins

`PropertyFinance.effective()` and `PropertySettings.effective()` are
structurally identical (§4, "Inheritable settings"). They differ only in
which group-level model they fall back to (`group.finance` vs
`group.settings`) and which fields are allow-listed.

The pattern itself ("nullable on the leaf, non-null on the group, resolve
via `effective()`") is good. Having it implemented twice means future
inheritable concepts will tend to grow a third copy.

**Direction:** extract an `Inheritable` mixin or a small descriptor that
takes `(group_attr, allowed_fields)`. Both PropertyFinance and
PropertySettings collapse to a one-line declaration each.

### 6.3. Booking archive: three signals for one concept

`Booking` carries `status`, `is_archived` (bool), and `archived_at`
(timestamp) (`reservations/models/booking.py:116–117`). The check
constraint at line 137 enforces that `archived_at` is only set when
`status` is terminal — meaning the three fields encode one concept three
times.

Callers must always check at least two of the three signals. The
constraints prevent inconsistency but don't prevent the cognitive overhead.

**Direction:** either fold "archived" into the `BookingStatus` enum as a
new terminal value, *or* drop `is_archived` and keep just `archived_at`
(present-and-non-null = archived). Either reduces the field count.

### 6.4. Booking's satellite models are scattered

Each Booking satellite lives in its own file at the top of
`reservations/models/`:

```
reservations/models/
  booking.py
  concierge.py     ← BookingConciergeItem
  enquiry.py
  guest.py
  preferences.py
  quotation.py
  terms.py
```

`BookingEvent`, `BookingNote`, `BookingHold`, and `BookingConciergeItem`
are all Booking children but read as peers of `Enquiry` and `Quotation` at
the directory level. File-per-model is good (CLAUDE.md endorses it); the
issue is that "what is a Booking, end to end?" is hard to answer from the
file tree.

**Direction:** a `reservations/models/booking/` subpackage that holds
`booking.py`, `event.py`, `hold.py`, `note.py`, `concierge.py`. Properties
already trends in this direction (`properties/models/` has 12+ files; a
sub-package would help there too).

### 6.5. EmailTemplate is not versioned

`EmailLog` is append-only and stamps a content hash, but
`EmailTemplate` is a regular `AuditedModel` — edits overwrite. The
audit log records *that* it changed, but not the prior text. Sent emails
keep their rendered body in `EmailLog`, so the *output* is recoverable;
the *input that produced it* is not, which makes "why did this email say
that?" harder to answer six months later.

**Direction:** an immutable `EmailTemplateVersion` table (content hash +
created_at) with `EmailTemplate` pointing at the current version. `EmailLog`
references the version that rendered it.

### 6.6. `SyncRecord` GenericFK trades type safety for flexibility

`SyncRecord` uses Django's `ContentType` + `object_id` pattern to attach
sync metadata to any model. The set of synced models is small and known
(properties, bookings, contacts, …). The cost: queries must build
`ContentType` lookups manually, and there's no FK constraint enforcing
referential integrity.

**Direction:** a per-target sync table (`SyncRecord_Property`,
`SyncRecord_Booking`, …) or a typed proxy layer. Loses some flexibility,
gains ORM clarity and integrity. Not urgent unless the GenericFK is
actively causing bugs.

### 6.7. Service-layer conventions live in CLAUDE.md, not in code

Idempotency stamps, permission checks, and audit-event emission are
*conventions*: a developer reading the design docs knows to apply them, but
nothing at the model or service layer enforces it. A new service that
forgets `actor_has_perm` or `meta["idempotency_key"]` looks fine in code
review.

**Direction:** a small `BaseService` class or decorators (`@idempotent`,
`@audited`, `@checks_permission("payments.refund")`) that wire in the
expected behaviour declaratively. Failure mode shifts from "review catches
it" to "service won't run without it".

### 6.8. Quotation property denormalisation

`Quotation.lines` is N:1 with `QuotationLine.property`. A single quotation
can technically span multiple properties. Whether that's intentional or
accidental is worth checking — in the legacy ResSystem, the implicit
assumption is that quotations are property-scoped.

If quotations are always single-property, storing `property_id` on
`Quotation` (with a check constraint that all lines match) makes lookups
cheaper and the invariant explicit.

### 6.9. Minor base-class drift

Most domain models extend `AuditedModel`. A handful (`NearbyPlaceType`,
`RoomBeds`, `FeatureCategory`, `SyncRecord`) extend only `TimestampedModel`
or neither. The lookup-tables-don't-need-audit rule is defensible, but it's
unwritten. Either codify it in `core/CLAUDE.md` or unify on `AuditedModel`.

---

## 7. Net assessment

The model is disciplined: explicit state machines, real `CheckConstraint`s,
no soft delete, a working audit registry, idempotent legacy loading. The
"big design decisions" are sound and well-defended in the design docs.

The friction is almost entirely in **de-duplication** (two `effective()`
patterns, three archive signals) and **polymorphism choices** (Payment vs
SecurityDeposit, GenericFK SyncRecord). Both are the kind of thing that
gets harder to fix the longer the codebase grows, but neither is causing
acute pain today.

The Property and Booking domains are starting to feel heavy at the
satellite-count level; a sub-package pass would help readability without
changing behaviour.
