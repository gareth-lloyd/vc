# 06 — Availability & Booking State Machine

The legacy system stored availability as one row per villa per day in `VillaAvailability` with four statuses (10/40/60/70). This redesign drops the daily grid entirely in favour of **range-query availability** backed by Postgres `EXCLUDE` constraints. The booking state machine is explicit, audited, and DB-enforced.

## Availability strategy: range queries, not a daily grid

### `BookingHold(SoftDeleteModel)` (in `reservations.models.booking`)
A soft reservation while a quotation is open or a booking awaits deposit. Replaces the legacy `OnHold` (status=40) rows in the daily grid.

- `property` — FK properties.Property CASCADE
- `quotation` — FK Quotation CASCADE, null=True
- `booking` — FK Booking CASCADE, null=True
- `date_from`, `date_to` — DateField
- `expires_at` — DateTimeField(db_index=True)
- `released_at` — DateTimeField(null=True, blank=True)
- `reason` — TextChoices (`QUOTATION_OPEN`, `BOOKING_DEPOSIT_PENDING`, `OWNER_BLOCK`, `MAINTENANCE`, `MANUAL`)

Constraints:
- `CheckConstraint(date_from < date_to)`
- `CheckConstraint(quotation IS NOT NULL OR booking IS NOT NULL OR reason IN ('OWNER_BLOCK','MAINTENANCE','MANUAL'))`
- `EXCLUDE USING gist (property_id WITH =, daterange(date_from, date_to, '[)') WITH &&) WHERE (released_at IS NULL AND expires_at > now())` — no overlapping live holds for a property
- An equivalent exclude on `Booking` (see 05-reservations.md) covers active bookings.

Together the two exclude constraints make double-booking impossible at the DB level.

### `AvailabilityService` (in `pricing.services`)

Why in `pricing`: change-over rules live there and need to be applied at quote time too.

```python
class AvailabilityService:
    @classmethod
    def is_available(cls, property, date_from, date_to, *, ignore_hold_ids=None) -> bool: ...

    @classmethod
    def conflicts(cls, property, date_from, date_to) -> list[Conflict]: ...

    @classmethod
    def calendar(cls, property, range_start, range_end) -> dict[date, CellStatus]: ...
```

Implementation of `is_available`:
1. Check no active Booking overlaps (status in active set, exclude constraint already enforces, but query confirms for UX).
2. Check no live BookingHold overlaps (`released_at IS NULL AND expires_at > now()`), optionally excluding hold ids we own (so a quotation can convert to a booking without fighting its own hold).
3. Check check-in date matches `ChangeOverRule` for the property (any rule for the active window must allow the weekday; if zero rules, all weekdays allowed).
4. Check `PropertySettings.min_nights_rental` (effective value after group fallback).
5. Return bool.

`calendar()` builds an on-demand grid for the admin UI from these queries — cheap with btree_gist indices.

### Hold lifecycle

```
created (QuotationService.create_from_enquiry)
  → released_at set      (released by HoldService.release on quotation cancel/expire/booking)
  → expires_at reached    (Celery beat task soft-deletes / sets released_at)
```

A Celery beat task `reservations.tasks.expire_holds` runs every minute:

```sql
UPDATE reservations_bookinghold
SET released_at = now()
WHERE released_at IS NULL AND expires_at < now()
RETURNING id, property_id, quotation_id;
```

The returning rows fan out to a signal so listeners can react (e.g. email "your hold has expired" — implemented as future scope).

## Booking state machine

`Booking.status` is a `TextChoices`. Transitions are methods on `Booking`. Every transition:
1. Asserts current status is in the allowed-from set.
2. Inside `transaction.atomic`, mutates fields and creates a `BookingEvent` row.
3. Fires a Django signal `booking_transitioned`.
4. Returns the booking.

### States

```python
class BookingStatus(models.TextChoices):
    DRAFT = "draft"
    PENDING_OWNER_APPROVAL = "pending_owner_approval"
    AWAITING_DEPOSIT = "awaiting_deposit"
    DEPOSIT_PAID = "deposit_paid"
    AWAITING_BALANCE = "awaiting_balance"
    BALANCE_PAID = "balance_paid"
    CHECKED_IN = "checked_in"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    DECLINED = "declined"     # owner rejection of a pending approval
```

### Transition table

| Method | From | To | Triggered by | Notes |
|---|---|---|---|---|
| `submit()` | DRAFT | PENDING_OWNER_APPROVAL | guest/agent | Skipped when property settings say bookings auto-approve |
| `auto_accept()` | DRAFT | AWAITING_DEPOSIT | system | If property `bookings_require_pre_approval=False` |
| `owner_approve()` | PENDING_OWNER_APPROVAL | AWAITING_DEPOSIT | owner | Sends initial-deposit email |
| `owner_decline(reason)` | PENDING_OWNER_APPROVAL | DECLINED | owner | Releases the BookingHold |
| `record_deposit(payment)` | AWAITING_DEPOSIT | DEPOSIT_PAID | payments signal | Locks the property dates (hold remains until balance) |
| `arm_balance()` | DEPOSIT_PAID | AWAITING_BALANCE | beat task | When within `balance_due_at` window |
| `record_balance(payment)` | AWAITING_BALANCE, DEPOSIT_PAID | BALANCE_PAID | payments signal | |
| `check_in()` | BALANCE_PAID | CHECKED_IN | admin / on date | |
| `complete()` | CHECKED_IN | COMPLETED | system on `date_to` | Triggers security-deposit refund flow |
| `cancel(reason)` | DRAFT, PENDING_OWNER_APPROVAL, AWAITING_DEPOSIT, DEPOSIT_PAID, AWAITING_BALANCE, BALANCE_PAID, CHECKED_IN | CANCELLED | guest/agent/admin | Refund policy + hold release handled in cancel logic |
| `expire()` | AWAITING_DEPOSIT | EXPIRED | beat task | When deposit deadline passes |

Terminal states: `COMPLETED`, `CANCELLED`, `EXPIRED`, `DECLINED`.

### Active states (used by DB exclude constraint)

`AWAITING_DEPOSIT`, `DEPOSIT_PAID`, `AWAITING_BALANCE`, `BALANCE_PAID`, `CHECKED_IN`. These rows participate in the no-overlap rule. The exclude constraint is partial: `WHERE status IN (...)`.

`PENDING_OWNER_APPROVAL` and `DRAFT` do not block the DB constraint but are protected by their `BookingHold` (which has its own exclude constraint).

### Why not django-fsm

- Adds a dependency for what amounts to: validate current state, mutate, log event, fire signal.
- The transition methods are easier to debug and customise individually.
- Status validation can live in a tiny helper:

```python
def _transition(self, allowed_from, to, *, actor=None, source="USER", reason="", **meta):
    if self.status not in allowed_from:
        raise InvalidTransition(self.status, to)
    with transaction.atomic():
        prev = self.status
        self.status = to
        self.save(update_fields=["status", "updated_at"])
        BookingEvent.objects.create(
            booking=self, from_status=prev, to_status=to,
            actor=actor, source=source, reason=reason, meta=meta,
        )
    booking_transitioned.send(sender=Booking, booking=self, from_status=prev, to_status=to,
                              actor=actor, source=source)
```

## Change-over rule enforcement

- Quote time: `PricingEngine.quote` calls `AvailabilityService.is_available(...)` (with `ignore_hold_ids` empty) so the engine refuses to quote unavailable or off-changeover dates.
- Booking creation: `BookingService.create_from_quotation_line` re-checks (the world may have changed since the quote).
- Admin override: `Booking.cancel` and `Booking.check_in` don't re-check; only creation does. An admin "force" path passes `force=True` which writes a `BookingEvent` with `meta={"force": true, "actor_reason": ...}` for audit.

## Owner block / maintenance

Modelled as `BookingHold` rows with `reason=OWNER_BLOCK` or `MAINTENANCE`, no `expires_at` (set to far future or special sentinel; or make `expires_at` nullable for these reasons specifically — choose at implementation time). They participate in the same `EXCLUDE` constraint, so no special-case query.

## Dropped from legacy

- `VillaAvailability` daily-row table — replaced by range queries over `Booking` and `BookingHold`.
- Status codes 10/40/60/70 — replaced by the BookingStatus enum and BookingHold semantics.
- The 7-day auto-release stored proc — replaced by `expire_holds` Celery task using `expires_at`.
- `UpdateAvailabilty` stored proc — never needed; the exclude constraint and transition methods handle it.
