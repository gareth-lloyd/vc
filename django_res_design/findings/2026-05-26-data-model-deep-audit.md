# Data Model Deep Audit — 2026-05-26

Companion to `2026-05-26-data-model-survey.md`. The survey describes shape;
this document hunts for **bugs, footguns, and concrete invariant holes**.

Each finding cites file + line and proposes a fix. Severity is calibrated to
the production impact of the bug actually firing, not how ugly the code is.

Severities: **🔴 Bug** (the schema allows invalid state, or a known race) —
**🟠 Footgun** (correct only if callers are careful; nothing enforces it) —
**🟡 Smell** (works today, will hurt later).

---

## 🔴 Bugs (the schema allows invalid state today)

### B1. `Booking.cancelled_at` constraint is one-directional

`reservations/models/booking.py:132–135`

```python
CheckConstraint(
    condition=Q(cancelled_at__isnull=True) | Q(status=BookingStatus.CANCELLED.value),
    name="booking_cancelled_at_implies_cancelled_status",
)
```

This says *"if `cancelled_at` is set, status must be CANCELLED"*. It does
**not** say the inverse. The schema allows
`status=CANCELLED, cancelled_at=NULL` — a cancelled booking with no record
of when it was cancelled. The `Booking.cancel()` service sets both, but
bulk updates, `update_or_create`, the legacy importer, and the admin can
land a row that violates the implicit invariant.

**Fix:** add the inverse constraint:
```python
CheckConstraint(
    condition=Q(cancelled_at__isnull=False) | ~Q(status=BookingStatus.CANCELLED.value),
    name="booking_cancelled_status_requires_cancelled_at",
)
```

### B2. `RateRule` allows zero-length date ranges

`pricing/models/rate.py:100–103`

```python
CheckConstraint(
    condition=Q(date_from__lte=F("date_to")),
    name="raterule_date_from_lte_date_to",
)
```

`__lte` allows `date_from == date_to` — a zero-night rule. Booking uses
strict `__lt` (`reservations/models/booking.py:128`). The pricing engine
will happily look up a rule with `[2026-06-01, 2026-06-01)` and either
return no rule (silent miss) or match it ambiguously depending on the
range semantics in the lookup query.

**Fix:** `Q(date_from__lt=F("date_to"))` to match Booking and QuotationLine.

### B3. `RateRule` lets `is_poa=True` coexist with a numeric price

`pricing/models/rate.py:108–113`

```python
CheckConstraint(
    condition=(
        Q(nightly__isnull=False) | Q(weekly__isnull=False) | Q(is_poa=True)
    ),
    name="raterule_price_or_poa",
)
```

Only the floor (at-least-one) is enforced. The schema accepts
`is_poa=True, nightly=500.00` — two contradictory signals. A pricing engine
that reads `is_poa` first will quote "POA"; one that reads `nightly` first
will quote £500. The "first-write-wins" bug surfaces only when somebody
forgets to clear `nightly` on a flip to POA.

**Fix:** add `~(Q(is_poa=True) & (Q(nightly__isnull=False) | Q(weekly__isnull=False)))`.

### B4. `PENDING_OWNER_APPROVAL` and `DRAFT` bookings can double-book *(fixed in migration 0007 + Booking._transition)*

`reservations/migrations/0002_postgres_exclude_constraints.py:36–46` and
`reservations/enums.py:88–94`

> **Status: resolved.** Migration `0007_booking_overlap_includes_pending_approval`
> drops the original `booking_no_overlap_active` constraint and replaces it
> with `booking_no_overlap_blocking`, which adds `pending_owner_approval`
> to the predicate. `Booking._transition`, `Booking.modify_dates`, and the
> `:convert` quotation flow translate the resulting `IntegrityError` into
> `OverlappingBooking` so callers see a 409 instead of a 500.

The (original) `booking_no_overlap_active` Postgres exclusion gates on:
```
status IN (awaiting_deposit, deposit_paid, awaiting_balance, balance_paid, checked_in)
```

`DRAFT` and `PENDING_OWNER_APPROVAL` are excluded. Two parallel owner
approval flows for overlapping dates both create
`PENDING_OWNER_APPROVAL` bookings; both are valid. When both owners
approve, the first transition to `AWAITING_DEPOSIT` succeeds; the second
fails with an opaque IntegrityError from the exclusion constraint.

This is a **race the customer experiences**: a quote was accepted, the
owner approved, then the system errors out because a faster booking won
the race.

**Fix:** include `PENDING_OWNER_APPROVAL` in the active set so two
overlapping approval-pending bookings are impossible from the moment they
exist. Or: enforce uniqueness at the `_assert_from` transition with
`SELECT ... FOR UPDATE` on overlapping rows. The constraint catching the
race is correct; the UX of *only* catching it at approve-time isn't.

### B5. Stale `BookingHold` rows can block valid bookings indefinitely

`reservations/migrations/0002_postgres_exclude_constraints.py:23–29`

```sql
EXCLUDE USING gist (property_id WITH =, daterange(date_from, date_to, '[)') WITH &&)
WHERE (released_at IS NULL);
```

The exclusion predicate is `released_at IS NULL`, not `expires_at > now()`.
The migration comment acknowledges this: Postgres won't allow `now()` in an
index predicate. The application is supposed to sweep expired holds and
set `released_at`. If the sweeper is paused (Celery beat down, queue
backed up, deploy rollback), expired-but-unreleased holds keep blocking
new bookings, and availability queries must compensate at every call site.

Today's mitigation is fragile. The risk is a single hung worker rendering
properties un-bookable until human intervention. A health check on
"oldest-unswept-expired-hold" would surface this; today there is none in
the model layer.

**Fix:** generate a materialised `is_active` boolean column via a trigger
or a periodic job, and gate the exclusion on that. Or accept the risk and
add a hard SLA + alerting on sweeper lag.

### B6. `Payment.unique_active_payment_per_purpose` covers only DEPOSIT and BALANCE

`payments/models/payment.py:98–110`

```python
UniqueConstraint(
    fields=["booking", "purpose"],
    condition=(
        Q(status__in=ACTIVE_PAYMENT_STATUSES)
        & Q(purpose__in=[PaymentPurpose.DEPOSIT.value, PaymentPurpose.BALANCE.value])
    ),
    name="unique_active_payment_per_purpose",
)
```

Two active `SECURITY_DEPOSIT` rows for the same booking are allowed. Two
active `CONCIERGE` rows are allowed. Whether that's right depends on
business semantics: a booking with multiple concierge items probably *is*
allowed to have multiple in-flight `CONCIERGE` payments, but
`SECURITY_DEPOSIT` should almost certainly be 1-per-booking. The constraint
name implies a general rule it doesn't actually enforce.

The dependency on `ACTIVE_PAYMENT_STATUSES` (a Python tuple at
`payments/enums.py:33`) is also brittle: adding a new status like
`AUTHORISED` requires remembering to update the tuple, otherwise the
constraint silently weakens.

**Fix:** decide per-purpose cardinality explicitly and add one constraint
per purpose that has a real cardinality rule. At minimum, scope
SECURITY_DEPOSIT.

### B7. Reference generation races and is bypassed by `bulk_create`

`core/refs.py:28–40`, used in `Payment.save()` (`payments/models/payment.py:119–122`)
and other anchors.

```python
def generate_reference(prefix, *, model=None):
    candidate = f"{prefix}-{year}-{_now_suffix()}"  # millis % 1_000_000
    if not model._default_manager.filter(reference=candidate).exists():
        return candidate
    return f"{prefix}-{year}-{_uuid_suffix()}"
```

Three problems stacked:

1. **TOCTOU race.** Two requests in the same millisecond both pass the
   `not exists` check and both insert. The `unique=True` on `reference`
   saves us with an IntegrityError — but the caller sees a 500, not a
   retry.
2. **Single-shot retry.** On collision the fallback is a UUID-derived
   suffix. If *that* also collides (vanishingly rare, but possible if the
   retry happens against the same row that just won the original race),
   there's no second retry — straight to IntegrityError.
3. **`bulk_create` bypass.** `save()` is the only place references get
   set. `bulk_create([Payment(), Payment()])` inserts with `reference=""`,
   which violates `unique=True` on the second row. The data migration
   loaders may hit this.

**Fix:** move reference generation to a Postgres sequence or a
`pre_save` signal that also fires inside `bulk_create` paths, and retry
the candidate generation rather than the falling-back-to-UUID branch.

### B8. `SecurityDeposit.damage_claim_id` is a hand-rolled FK without integrity

`payments/models/security_deposit.py:71–72`

```python
# TODO: convert `damage_claim_id` to FK("reservations.DamageClaim", on_delete=SET_NULL)
damage_claim_id = models.PositiveBigIntegerField(null=True, blank=True)
```

There is no FK constraint. If `DamageClaim` rows are deleted (or never
existed because the model hasn't shipped yet), `damage_claim_id` keeps
pointing at nothing. There's no `select_related`, no cascade, no DB-level
guarantee. The TODO has been there long enough to be worth fixing or
removing the field.

**Fix:** ship the FK. If `DamageClaim` doesn't exist yet, leave the field
nullable, but stop pretending it's referential.

---

## 🟠 Footguns (correct only if callers are careful)

### F1. `Booking` and `Quotation` currencies are independent

`reservations/models/booking.py:63–67`, `reservations/models/quotation.py:42–46`

Both anchor models have their own `currency` FK to `pricing.Currency`. No
constraint enforces that a Booking promoted from a QuotationLine matches
the source Quotation's currency. The conversion service is supposed to
copy it; nothing catches a regression.

Worse: `Booking.modify_dates()` re-runs pricing inside
`@transaction.atomic` (`reservations/models/booking.py:387–437`) using
`self.currency` as the snapshot input. If the property's RatePlan currency
has been changed since the booking was created (or if some buggy import
flips Booking.currency), the recomputed `balance_due` is in a different
currency than the customer was originally quoted in. There is no
"currency-locked" flag.

**Fix:** at minimum, a CheckConstraint that `Booking.currency_id ==
source_quotation_line.quotation.currency_id` via a denormalised column. A
"booking is currency-locked at confirmation" invariant would be even
stronger.

### F2. The `effective()` resolver treats `""` and `NULL` as both meaning "inherit"

`properties/models/finance.py:36–41`, `properties/models/settings.py:79–89`

```python
def effective(self, field):
    own = getattr(self, field)
    if own is not None and own != "":
        return own
    return getattr(group, field)
```

For a `CharField` with `null=True, blank=True`, both `NULL` and `""` fall
through to the group. A user who *intentionally* clears a property's
override (override = empty string, not inherit) cannot express that — the
resolver always reads it as inherit. There's no way to say "this property
explicitly has no bank account note" if the group has one.

Either the inherit-state is `NULL` only and `""` is an explicit override,
or it's the union — but the code's behaviour and the field's `null=True,
blank=True` aren't telling the same story. Today's behaviour silently
prefers the group, which is fine until it isn't.

**Fix:** pick one. Use `NULL` for inherit, disallow `""`, and update the
factories/migrations. Or add a `<field>_inherits` boolean per inheritable
field (heavier, but unambiguous).

### F3. `effective()` crashes if `property.group` is null

`properties/models/finance.py:39`, `properties/models/settings.py:88`

```python
return getattr(self.property.group.settings, attr)
```

If `Property.group_id` is nullable and ever NULL (which is unclear from
the model — worth checking), this resolver will `AttributeError` on the
first inheritable field anyone reads. Same for `group.settings` and
`group.finance` 1:1 rows that don't exist yet (e.g. mid-migration). The
fallback assumes a fully-populated group, but there's no constraint that
guarantees one.

**Fix:** make `Property.group` non-nullable (and migrate orphans to a
`default` group), or have `effective()` return a hard-coded default when
the group is missing.

### F4. `Payment.purpose` rows share fields that only make sense for some purposes

`payments/models/payment.py:39–110`

The single-table polymorphism (see survey §5) means every row carries every
field even when the field is meaningless. Specifically:

- `due_at` only makes sense for forward-looking purposes
  (DEPOSIT, BALANCE, SECURITY_DEPOSIT). A `REFUND` row with `due_at` set
  is nonsense.
- A `concierge_item` FK presumably only applies when
  `purpose=CONCIERGE` (verify the field exists).
- A REFUND row's `amount` is conceptually negative, but
  `DecimalField(max_digits=12, decimal_places=2)` has no sign constraint
  — sign convention lives in code.

No CheckConstraint enforces "this combination of (purpose, field-set) is
valid". The state machine has all the rules; the DB has none of them.

**Fix:** per-purpose CheckConstraints, e.g.
`~(Q(purpose=REFUND) & Q(due_at__isnull=False))`.

### F5. `IdempotencyRecord.user` is required — system actors can't dedupe

`core/models/idempotency.py:22–26`

```python
user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=PROTECT)
```

The unique key is `(user, path, key)`. System actors (`actor=None` in the
service layer convention) can't write an idempotency record because
`user` is required. Webhook retries from Stripe — the canonical
idempotency use case — don't have a user. Today this is presumably
papered over by having webhooks use a different dedupe path (e.g.
provider_reference uniqueness), but the design says "use this table" and
the schema says "you can't".

**Fix:** make `user` nullable and switch the unique constraint to use
`COALESCE(user_id, 0)` or include a `scope` field
(`USER`, `WEBHOOK`, `SYSTEM`) in the key.

### F6. `Booking.modify_dates` and `modify_guests` re-run pricing without row locks

`reservations/models/booking.py:387–493`

Both methods wrap the work in `@transaction.atomic`, but neither takes a
`select_for_update()` on the Booking row. Two parallel "modify dates"
requests can interleave: T1 reads dates, T2 writes new dates, T1 reruns
pricing using *its* read of dates, T1 writes — overwriting T2's dates
with stale pricing.

Postgres' default isolation (`READ COMMITTED`) won't save you here; you
need `SERIALIZABLE` or explicit row locks.

**Fix:** start the transaction with
`Booking.objects.select_for_update().get(pk=self.pk)` and operate on that
instance.

### F7. `SyncRecord` GenericFK leaves dangling rows when targets are deleted

`integrations/models/sync_record.py` (model uses ContentType + object_id)

`Contact.merge()` hard-deletes the absorbed contact. `Quotation` can be
hard-deleted. There is no signal handler in the integrations app that
deletes `SyncRecord` rows pointing at the deleted target. After a merge,
`SyncRecord.object_id` points at nothing; queries get silent-empty
results when they try to resolve `.target`.

This is the textbook GenericFK failure mode and the model doesn't address
it.

**Fix:** a `pre_delete` signal in `integrations.apps.ready()` that
removes `SyncRecord` rows for the deleted instance. Or move to typed
sync tables (one per synced model).

### F8. `PropertySettings.check_in_time` / `check_out_time` have no timezone

`properties/models/settings.py:59–60`

```python
check_in_time = models.TimeField(null=True, blank=True)
check_out_time = models.TimeField(null=True, blank=True)
```

`TimeField` is naive. `Property` has no `timezone` column visible from
the survey. Two villas in different timezones with `check_in_time='16:00'`
are indistinguishable in the schema. Pricing changeover, availability
windows, and reminder emails (already in the comms templates) that need
to know "how many hours until check-in" can't compute it from the
booking + property alone.

**Fix:** add `Property.timezone` (or `PropertyLocation.timezone`) and
treat `check_in_time` as wall-clock-in-that-timezone everywhere.

---

## 🟡 Smells (works today, will hurt later)

### S1. `Booking.archived_at` constraint allows pre-archived bookings to be archived

`reservations/models/booking.py:136–139`

The constraint says `archived_at IS NULL OR status ∈ TERMINAL`. Combined
with the lack of an inverse on cancelled (B1), the archive bit is a
"second status" that the schema only loosely couples to status. If folded
into the status enum (`ARCHIVED` value, or `CANCELLED_ARCHIVED` etc.),
the whole question goes away. Already raised in the survey §6.3.

### S2. `Quotation` lifecycle bypasses `Quotation.cancel()` for `EXPIRED`

`reservations/models/quotation.py:119–122`

`expire()` is `SENT → EXPIRED` only. A `DRAFT` quotation that ages past
`expires_at` cannot expire — only `cancel()` works. The Celery beat that
expires quotations needs to know to also clean up DRAFTs, but the model
doesn't let it. Minor, but a hole in the state machine.

### S3. `Currency.decimal_places` is informational, not enforced

`pricing/models/currency.py` exposes `decimal_places` per currency. Money
fields on Payment, RateRule, etc. use a fixed
`DecimalField(max_digits=12, decimal_places=2)`. A JPY amount of `100.00`
fits the field but violates the currency's own metadata. No code path
appears to coerce on save.

**Fix:** quantize amounts to `currency.decimal_places` in service-layer
write paths, or store amounts as integer minor units (the "always work in
pence" pattern) and derive decimal display from the currency.

### S4. `EmailLog` content hash is the only post-hoc identifier

The survey notes templates aren't versioned. Add to that: the content
hash on `EmailLog` is over `(template_key, sorted(to), correlation)` —
*not* the rendered body. Two emails sent from the same template with the
same recipients dedupe even if the rendered output is different
(different `context`). Probably what's wanted, but worth confirming the
contract is "one-template-render-per-correlation" and not "one
distinct-body-per-correlation".

### S5. `Property.country_code` vs `hotel.country` — verify legacy field is gone

CLAUDE.md says to use `hotel.country_code` with `get_country()`, not
`hotel.country` (free-text string). I didn't see a `country` free-text
field on `Property` in this audit, but the rule's existence implies it
either lived in the legacy schema or still lurks somewhere. Worth a grep
to confirm there's no residual `country = CharField(...)` waiting to bite
a future developer who follows the wrong column.

### S6. `Booking.terms_accepted_at` is required but has no default

`reservations/models/booking.py:107`

Required, non-null `DateTimeField` with no `auto_now_add`, no service-level
guarantee. Factory code and the API must remember to set it. The error
when forgotten is a generic `IntegrityError: NOT NULL constraint failed`,
not a domain-meaningful "terms not accepted". Minor UX issue at the
service layer.

---

## What to fix first

If I had a week of cleanup time, in order:

1. **B4** — owner-approval race causes real customer-visible failures.
2. **B7** — reference generation under `bulk_create` is a ticking bomb for
   data migration / cutover.
3. **B6** — Payment uniqueness rules are subtly wrong; security deposits
   are real money.
4. **F1** — currency consistency between Booking and Quotation.
5. **F6** — `select_for_update` on Booking modifications.
6. **B1, B2, B3** — three lines of constraint fixes, each closing a real
   hole. Cheap.

The rest are best handled the next time their app is touched, rather than
as a sweeping cleanup pass.

---

## What I'd want to investigate further

Things I noticed but didn't fully chase:

- **PropertyContactAssignment M2M** — does it have a "role" field with
  enum, and is a contact allowed to be `OWNER` on multiple groups? Owner
  uniqueness per property is probably an invariant.
- **`pricing.RateRule` priority field** — overlapping rules are explicitly
  allowed (the `priority` field implies tie-breaking). The pricing engine
  must read the highest-priority match; is that behaviour tested?
- **`Refund.amount` sign convention** — refund rows in the unified ledger
  likely store positive amounts with a purpose tag. The booking balance
  computation has to know to subtract them. Worth confirming the
  invariant lives somewhere.
- **`integrations.SyncRun` / `SyncIssue`** — not audited; failed sync
  cleanup and retry behaviour matter for Zoho integrity.
- **`legacy_id` indexing** — survey says present on every importable
  model. Verify it's `db_index=True` and the data migration uses it
  consistently as the natural key.
