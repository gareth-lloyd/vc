# Data Model Overview

> **Canonical: what the backend is today.** This is the living, as-built map of
> the `django_res/` data model — the doc to trust when the field-level specs
> under [`backend/`](backend/) (frozen design-time rationale) disagree with it.
> The full truth is this doc + the code in `django_res/` + the open work in
> [`../todo/INDEX.md`](../todo/INDEX.md). Keep it in sync with the code.

A descriptive map of the backend data model in `django_res/`: the
fundamental building blocks, how they fit together, and the cross-cutting
patterns that recur across apps.

This is orientation, not a spec — keep it in sync with the code as the
model evolves. Known issues and planned changes live in
[`../todo/`](../todo/INDEX.md); this document only describes what exists.

---

## 1. Apps and their domains

| App | Domain | Anchor model(s) |
|---|---|---|
| `accounts` | Auth users, the unified `Person` identity (booking-side customers + owners/agents/managers), sessions, RBAC | `User`, `Person` |
| `properties` | The villa catalogue + per-property settings/finance (seeded from a global `PropertyDefaults` singleton) + geography | `Property` |
| `pricing` | Three-tier price model + surcharges/discounts + FX | `RatePlan` → `RatePeriod` → `RateBand` |
| `reservations` | Enquiry → Quotation → Booking lifecycle, plus guests, terms, holds, concierge | `Booking`, `Quotation` (customer = `accounts.Person`) |
| `payments` | Unified payment ledger + events + refunds + webhooks + security deposit | `Payment` |
| `comms` | Email sending (SMTP profiles, templates, append-only log) | `EmailLog` |
| `integrations` | Generic sync metadata, Zoho OAuth, sync run audit | `SyncRecord` |
| `core` | Shared base classes, audit registry, idempotency helpers, reference generation | `TimestampedModel`, `AuditedModel`, `AuditLog` |

## 2. Anchor models

Five models carry the weight of the system:

- **`Property`** — focal point for pricing, settings, finance, rooms, images,
  features, and contact assignments. Has the largest "satellite cluster":
  `PropertySettings`, `PropertyFinance`, `PropertyCapacity`, `Room`,
  `PropertyImage`, `PropertyDescription`, `PropertyLocation`, plus M2M to
  `Person` (kind=CONTACT) via `PropertyContactAssignment`.
- **`Booking`** — central to reservations. Has its own satellite cluster:
  `BookingEvent`, `BookingNote`, `BookingHold`, `BookingConciergeItem`,
  `BookingDocument`, and a 1:N to `Payment`. Its historic cousin
  **`PastStay`** (GAP-089) is a Person-owned record of a stay imported from Nick's spreadsheets — villa
  name (+ optional resolved `Property`), year, legacy booking number, no
  dates or money — surfaced on Customer-360 and counted into the
  repeat-customer flag, never scheduled, invoiced or pushed to Zoho.
- **`Person`** (`accounts`) — the single unified human-identity model. A
  `kind` enum (`CUSTOMER` vs `CONTACT`) distinguishes booking-side customers
  (across Enquiry → Quotation → Booking) from operator-side owners/managers/
  agents. Has an optional `OneToOne` to `User`; PII-anonymizable. Email/phone
  live in `PersonEmail` / `PersonPhone` child rows. (Formed by renaming the
  old `Contact` model to `Person`, then folding the former `Guest` into it —
  GAP-045.)
- **`Payment`** — single-table polymorphic ledger keyed on a `purpose` enum
  (`DEPOSIT` | `BALANCE` | `SECURITY_DEPOSIT` | `CONCIERGE` | `REFUND` |
  `ADJUSTMENT`).

Every other model is best understood as either a satellite of one of these
anchors, a lookup/config row, or a cross-cutting audit/sync record.

## 3. Relationships (high-level)

```
Property ─1:N→ RatePlan ─1:N→ RatePeriod ─1:N→ RateBand
           RatePlan = date-less regime bucket, one *active* per (property,
           currency, price_basis); RatePeriod = the sole date axis, carrying
           property + currency stamped from its plan, no-overlap per
           (property, currency) whatever the plan (GAP-110)
         ─1:1→ PropertySettings, PropertyFinance, PropertyCapacity
         ─1:N→ Room, PropertyImage, PropertyDescription, PropertyLocation
         ─M:M→ Person (via PropertyContactAssignment)
         ─M:M→ Feature, Collection

Room ─M:M→ RoomAttribute (via RoomAttributeAssignment; amenity catalog,
           GAP-064 — RoomAttribute.implies_property_feature bridges to Feature)
Room location = two orthogonal blank-able axes (GAP-065): placement (building)
           + floor (ladder); raw legacy string preserved in placement_note

Enquiry ─1:N→ Quotation ─1:N→ QuotationLine ─1:N→ Booking
Person  ─1:N→ Quotation, Booking            (customer; also User OneToOne)
Person  ─1:N→ Quotation.agent, Booking.agent (agent; also User OneToOne)

Booking ─1:N→ Payment, BookingHold, BookingEvent, BookingNote, BookingConciergeItem,
              BookingDocument (GAP-094; CASCADE, private `documents` storage alias)
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
(`NearbyPlaceType`, `RoomBeds`, `FeatureCategory`, `RoomAttribute`,
`SyncRecord`) extend only `TimestampedModel` or neither.

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

### Property settings/finance defaults (no runtime inheritance)
There is no property-group inheritance. A global `PropertyDefaults` singleton
(`properties/models/defaults.py`, `pk=1` via `get_solo()`, mirroring
`core.SystemSettings`; `GET/PATCH /property-defaults`, `IsReservationsWriter`)
holds the starter values for both `PropertySettings` and the finance-policy
columns of `PropertyFinance`. At property creation those values are
**snapshotted field-by-field** into the concrete rows
(`properties/services/defaults.py::snapshot_defaults`, wired into
`PropertyViewSet.create` and `PropertyLifecycleService.duplicate`); after the
snapshot the rows are plain, independently-editable attributes and editing a
default never re-flows into existing properties (GAP-070, dropped property
groups + `effective()` inheritance).

`None` on a `PropertySettings` / `PropertyFinance` column now means *genuinely
unset*, not "inherit":

- `PropertySettings` consumers apply a hardcoded final floor at the point of
  use where one exists (`hold_duration_hours`→48, `changeover_day`→`ANY`,
  `prices_entered_as`→`GROSS`, `min_nights_rental`→1,
  `availability_default`→`AVAILABLE`, `bookings_require_pre_approval`→`False`;
  `currency` / check-in/out stay nullable). There is no model-level
  `effective()` resolver.
- `PropertyFinance` resolves a `NULL` policy column to the frozen pre-GAP-070
  legacy floor via `PropertyFinance._policy(field)` reading the
  `_POLICY_FALLBACKS` dict (deliberately *not* identical to the
  `PropertyDefaults` starter values — e.g. `security_deposit_required` floor
  `False` vs `True` in the singleton).

`PropertyFinance` still exposes the per-concern builder resolvers
`effective_commission()`, `effective_tax_policy()`,
`effective_payment_schedule()`, `effective_security_deposit_policy()`,
`effective_bank_account()`, and `effective_cancellation_policy()` — the names
are kept (payments / reservations / pricing / the settings serializer call
them), but they now read own fields + `_POLICY_FALLBACKS` rather than merging a
group.

### Guest-facing documents (`BookingDocument`, GAP-094)
`BookingDocument(booking CASCADE, kind, file, generated_at, generated_by,
sent_to_guest_at)` — one row per generate, never overwritten, newest first;
`BookingDocumentKind` names all five spec values but only `CONTRACT` renders
today. The bytes are a WeasyPrint PDF (`core.pdf.html_to_pdf`) written to a
dedicated **private** `STORAGES["documents"]` alias — the default bucket is
world-readable and unsigned, and a contract carries guest PII — and served
only by streaming through the staff-permissioned API; no URL to them exists.
Confirmation auto-generates and emails the contract (`booking.contract`, the
PDF attached, correlation `{booking_id, document_id}`); `sent_to_guest_at`
means "handed to the mail pipeline" — stamped when the `EmailLog` comes back
`QUEUED` **or** `SENT` (eager dispatch, which is what staging runs, never
leaves a row `QUEUED`), never on `FAILED` or allowlist-`BLOCKED`. **Only an
unsent document can be deleted** (`DELETE …/documents/{id}`, gap-094-retro):
the `EmailLog` that carried it references the blob by storage key and a
resend re-reads it, so a stamped row answers 409 `document_sent`. The
service re-reads the row under `select_for_update` before deciding; the row
goes inside the transaction (audit tombstone via `track`) and a
`post_delete` receiver releases the PDF `on_commit` through
`core.storage.release_stored_file_after_commit` — so cascades and admin
deletes release it too — logging, never raising, on a storage fault.
`Booking.has_been_confirmed()` (status ∈ `CONFIRMED_BOOKING_STATUSES`, else
the `BookingEvent` trail) is the one "confirmed" predicate: the generate
guard and the detail serializer's `has_been_confirmed` both use it, and the
Documents tab warns when a confirmed booking has no contract on file.
Environment faults are system checks: `reservations.E001` (WeasyPrint's
native toolchain / fonts; `W001` under DEBUG) fails Render's `migrate`
pre-deploy instead of every confirmation silently producing no contract.

**Content is snapshotted, not referenced.** `Booking.house_rules_snapshot`
(TextField, blank) is stamped on the first entry to `AWAITING_DEPOSIT`: the
two confirming transitions (`auto_accept` / `owner_approve`) call
`Booking._house_rules_stamp()`, which reads the property's `HOUSE_RULES`
`PropertyDescription` via `live_house_rules()`, and pass it to `_transition`
as `extra_updates` so the write lands on the same `save()` as the status
change. (`_transition` is generic — the house-rules read is at the call site,
not in it.) Every contract renders from that column, so editing a property's
house rules cannot retroactively rewrite a contract a guest already agreed
to. `house_rules_snapshot_at` (nullable) is stamped with every genuine
snapshot by `house_rules_stamp()`; a non-empty body with a **null**
timestamp was reconstructed by the `0010` backfill from the property's
then-current rules, and the contract labels it as such rather than
"Recorded at confirmation on <date>" (`Booking.house_rules_reconstructed`).
`PropertyFactory` seeds no house rules unless `with_house_rules=True`.
Same instinct as `snapshot_defaults` above and
`Booking.pricing_snapshot`: a document that outlives its source copies the
source. House rules reach no public payload, pinned by sentinel tests across
the Zoho villa/booking payloads, the WordPress intake response, the
quote-options serializer and the owner-portal serializer.

### Idempotency
- ~~`IdempotencyRecord` table — used at the HTTP boundary~~ — dropped per
  FG-005 (2026-07-02): it never gained a runtime writer; dedupe lives in the
  meta-key path below.
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
- `Person` uses `status` (`PersonStatus`: ACTIVE / INACTIVE / ANONYMIZED) +
  `anonymized_at` + `anonymize()` for PII erasure.
- Hard deletes are paired with `AuditLog` rows (e.g. `Person.merge`).

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
decision — see [Q-016](../todo/done/q-016-payment-ledger-vs-dedicated-models.md).
