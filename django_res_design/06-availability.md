# 06 — Availability & Booking State Machine

The legacy system stored availability as one row per villa per day in `VillaAvailability` with four statuses (10/40/60/70). This redesign drops the daily grid entirely in favour of **range-query availability** backed by Postgres `EXCLUDE` constraints. The booking state machine is explicit, audited, and DB-enforced.

## Availability strategy: range queries, not a daily grid

### `BookingHold(AuditedModel)` (in `reservations.models.booking`)
A soft reservation protecting a villa's dates. Replaces the legacy `OnHold` (status=40) rows in the daily grid.

> **Holds are a manual operator action — quotations never place them automatically.** Quoting is the soft part of the sales process (legacy parity: the quote generator's explicit Hold / Remove-hold buttons): creating, duplicating, or editing a quotation line never blocks availability, and a quote may legitimately be saved over dates someone else holds. An operator places a line's hold deliberately via `POST /quotations/{qid}/lines/{id}:hold` (`QuotationService.hold_line` — idempotent, reason `QUOTATION_OPEN`, expiry from the property's effective `hold_duration_hours`, ~48h default) and releases it via `:release-hold` (never status-guarded — freeing inventory must always be possible). Editing a held line's dates *moves* the live hold (`move_line_hold`, preserving its expiry); editing an un-held line never conjures one.

**Lifecycle is the `released_at` timestamp**, not a soft-delete flag. Live holds satisfy `released_at IS NULL AND expires_at > now()`; expired or manually released holds carry a `released_at` value and are visible to any query that wants them (the partial `EXCLUDE` index simply excludes them from the no-overlap rule). The Celery `expire_holds` beat task sets `released_at = now()` on expired rows — it does not delete them.

- `property` — FK properties.Property CASCADE
- `quotation` — FK Quotation CASCADE, null=True
- `booking` — FK Booking CASCADE, null=True
- `date_from`, `date_to` — DateField
- `expires_at` — DateTimeField(db_index=True)
- `released_at` — DateTimeField(null=True, blank=True)
- `reason` — TextChoices (`QUOTATION_OPEN`, `BOOKING_DEPOSIT_PENDING`, `OWNER_BLOCK`, `MAINTENANCE`, `MANUAL`, `STOP_SALE`)

Constraints:
- `CheckConstraint(date_from < date_to)`
- `CheckConstraint(quotation IS NOT NULL OR booking IS NOT NULL OR reason IN ('OWNER_BLOCK','MAINTENANCE','MANUAL','STOP_SALE'))`
- `EXCLUDE USING gist (property_id WITH =, daterange(date_from, date_to, '[)') WITH &&) WHERE (released_at IS NULL AND expires_at > now())` — no overlapping live holds for a property
- An equivalent exclude on `Booking` (see 05-reservations.md) covers active bookings.

Together the two exclude constraints make double-booking impossible at the DB level.

### `AvailabilityService` (in `reservations.services`)

Why in `reservations`: it reads `Booking` / `BookingHold` occupancy directly, so homing
it here keeps `pricing` free of any upward `pricing → reservations` import (the cycle
that move dissolved). Change-over times are still resolved from property settings and
applied at quote time.

```python
class AvailabilityService:
    @classmethod
    def is_available(cls, property, date_from, date_to, *, ignore_hold_ids=None) -> bool: ...

    @classmethod
    def conflicts(cls, property, date_from, date_to) -> list[Conflict]: ...

    @classmethod
    def calendar(cls, property, range_start, range_end) -> dict[date, CellStatus]: ...

    @classmethod
    def multi(cls, property_ids, date_from, date_to) -> tuple[holds_qs, bookings_qs]: ...
```

`multi()` (shipped) feeds the multi-villa timeline (`GET /availability`): raw overlapping
**range bands** across up to 50 properties — live holds via `BookingHold.live_overlapping`
(booking-linked holds excluded as a one-band-per-stay guard) and occupying bookings via
`Booking.objects.occupying` (so resting legacy `DRAFT` rows show). No per-day cells: the
frontend derives display status and geometry from the intervals.

Implementation of `is_available`:
1. Check no Booking *occupies* the range (`Booking.objects.occupying` — any status **not** in `TERMINAL_BOOKING_STATUSES`). This is deliberately broader than the DB `OVERLAP_BLOCKING` write-constraint set: it also catches resting `DRAFT` rows (see below) that the constraint lets overlap.
2. Check no live BookingHold overlaps (`released_at IS NULL AND expires_at > now()`), optionally excluding hold ids we own (so a quotation can convert to a booking without fighting its own hold).
3. Check check-in date matches `ChangeOverRule` for the property (any rule for the active window must allow the weekday; if zero rules, all weekdays allowed).
4. Check `PropertySettings.min_nights_rental` (effective value after group fallback).
5. Return bool.

`calendar()` builds an on-demand grid for the admin UI from these queries — cheap with btree_gist indices.

#### `CellStatus` — the operator-facing display vocabulary

`CellStatus` is the *display* status each calendar cell surfaces; it is not a stored field. It is derived per-date from the underlying `Booking.status` plus any live `BookingHold.reason`, giving operators the vocabulary agreed on the 2026-05-29 stakeholder call: **Available / On Hold / Booked / Booked-VC / Stop Sale** (see `10-decisions.md` "Stop Sale in the availability display vocabulary").

```python
class CellStatus(models.TextChoices):
    AVAILABLE = "available"      # no active booking, no live hold
    ON_HOLD = "on_hold"          # live hold, reason QUOTATION_OPEN / BOOKING_DEPOSIT_PENDING / MANUAL (short-term)
    BOOKED = "booked"            # active Booking, non-VC origin
    BOOKED_VC = "booked_vc"      # active Booking of VC origin
    STOP_SALE = "stop_sale"      # live hold, reason OWNER_BLOCK / MAINTENANCE / STOP_SALE (persistent owner/operator block)
```

Derivation precedence: an active `Booking` wins (→ `BOOKED` / `BOOKED_VC`); otherwise a live persistent block hold (`OWNER_BLOCK` / `MAINTENANCE` / `STOP_SALE`) → `STOP_SALE`; otherwise a live short-term hold (`QUOTATION_OPEN` / `BOOKING_DEPOSIT_PENDING` / `MANUAL`) → `ON_HOLD`; otherwise `AVAILABLE`.

`BOOKED_VC` is a presentation distinction drawn from a Booking's origin (`site_source` / VC-internal), **not** a separate model — there is no `Booking.status` value for it. `STOP_SALE` is likewise a presentation reconciliation over the persistent block reasons rather than a new hold mechanism; the only model-level addition is the optional `STOP_SALE` `reason` value (above), used when a Stop Sale must be distinguished from an internal owner-block/maintenance in reporting.

> **Timeline note.** The shipped multi-villa timeline (`02-frontend-design.md` §3.5) renders **three** of these statuses — Booked / On hold / Stop sale (available is blank) — derived client-side from the `multi()` bands. `BOOKED_VC` is deferred there: the legacy loader never set `site_source`, so every migrated booking reads as `main_website` and the split would mislabel the whole historical portfolio. Reintroduce it when a trustworthy origin signal exists.

> **Implementation note.** The shipped `CellStatus` (`reservations/services/availability.py`) is a `@dataclass`, not a `TextChoices` — it carries `available: bool`, a `reason` string (`booked` / `owner_block` / `maintenance` / `manual` / `quotation`), an optional `block_id` (the originating editable `BookingHold` pk), and the optional `segments` split described next. The five-word vocabulary above is the operator-facing *labelling* that the frontend derives from these fields; treat the dataclass as the wire shape.

#### Half-day turnover — `CellStatus.segments`

A cell can split into an **AM** (departing) and **PM** (arriving) half via an optional `segments={"am": CellStatus, "pm": CellStatus}` mapping. The split is presentation-only and is gated on the property allowing same-day changeover (effective `check_out_time` earlier than `check_in_time`, resolved once per calendar via `PropertySettings`). `_apply_changeover_segments` populates it on two kinds of day:

1. **True changeover** — one interval's exclusive checkout (`date_to`) coincides with another's check-in (`date_from`). Both halves are occupied; the day stays `available=False`. Works for any reason mix (booking-meets-booking, booking-meets-block, etc.).
2. **Lone booking checkout** — a **native VC booking's** `date_to` with no arriving stay that day. The departing guest holds the morning (`am = booked`) but the afternoon is sellable as a new arrival (`pm` available), so the cell stays **`available=True`**. Catalogue search and `is_available` ignore `segments`, so the day remains genuinely bookable.

**Only native bookings turn over.** An owner/maintenance/manual block — and every iCal-imported block — has no sellable checkout to split, so all blocks render **whole-day** regardless of changeover settings. (Distinguishing iCal "bookings" from "closures" to give the former turnover is a separate future feature; imported blocks deliberately collapse the distinction today — see `integrations/ical/profiles.py`.)

#### Search & filter UX

When the quote-builder or operator search runs a query over properties for a given date range, the result list:

- **Hides unavailable properties by default.** Legacy returned available + unavailable interleaved, which slowed the agent's eye as they scanned long result sets. New default is available-only.
- **Surfaces a "Show unavailable" toggle** for the legacy behaviour. Operators occasionally need to see unavailable inventory (to recognise the villa they were going to suggest, or to offer it for a different week) — the toggle keeps that reachable, just behind one click.
- **Includes flexible-changeover (`PropertySettings.changeover_day = ANY`) properties on every weekday query.** A confirmed legacy bug filtered these out of specific-weekday searches — see `09-departures.md` "Legacy correctness bugs explicitly fixed" #3 and `02-properties.md`.

The search layer itself does not call `AvailabilityService.is_available()` per property (too expensive on large result sets). It instead applies an indexed query against `Booking` + `BookingHold` for the date range, joins to `Property`, and yields the unavailable-property ids as a set; the result paginator can use that set to omit them (default) or visually gray them out (toggle on).

### Hold lifecycle

```
created (operator action: lines/{id}:hold → QuotationService.hold_line,
         or an operator block via the availability endpoints)
  → released_at set      (operator :release-hold; line delete signal;
                          quotation :withdraw; booking conversion)
  → expires_at reached    (Celery beat task sets released_at = now())
```

Quotation **expiry** does *not* release line holds: a hold carries its own
`expires_at` (the property's effective `hold_duration_hours`) and is reaped by
`expire_holds` independently. A hold may therefore outlive its quotation —
deliberate, since the operator placed it as a significant action — and
`:release-hold` works on a quotation in any status for exactly that reason.
Withdrawal (`:withdraw`) and conversion to a booking still release every hold
on the quotation immediately.

A Celery beat task `reservations.tasks.expire_holds` runs every minute:

```sql
UPDATE reservations_bookinghold
SET released_at = now()
WHERE released_at IS NULL AND expires_at < now()
RETURNING id, property_id, quotation_id;
```

The returning rows fan out a `hold_expired(hold)` Django signal. The `comms` app listens (see `10-comms.md`) and dispatches a `hold.expired` email to the agent who created the hold. Auto-expiry is **enabled from day one** — the legacy scheduler was `[DISABLED]` (see `workflows/06-availability/holds.md`), which forced manual cleanup. This Celery beat task replaces that gap.

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
    CHECKED_OUT = "checked_out"  # final post-stay state (replaces the older `COMPLETED`); reached by manual `check_out()` or the auto-completion beat task
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    DECLINED = "declined"     # owner rejection of a pending approval
```

`is_archived` is a separate boolean flag on `Booking` (with `archived_at` timestamp) — **not** a status value. Archive is orthogonal to the state machine: it tidies a terminal-state booking out of the operator's default list view. See `:archive` / `:restore` below.

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
| `check_out()` | CHECKED_IN | CHECKED_OUT | admin / system beat task on `date_to` | Triggers security-deposit refund flow. Same method whether called manually by ops (early/late departures) or by the auto-completion beat job — both paths converge on `CHECKED_OUT`. |
| `cancel(reason)` | DRAFT, PENDING_OWNER_APPROVAL, AWAITING_DEPOSIT, DEPOSIT_PAID, AWAITING_BALANCE, BALANCE_PAID, CHECKED_IN | CANCELLED | guest/agent/admin | Refund policy + hold release handled in cancel logic |
| `expire()` | AWAITING_DEPOSIT | EXPIRED | beat task | When deposit deadline passes |

Terminal states: `CHECKED_OUT`, `CANCELLED`, `EXPIRED`, `DECLINED`.

### Non-transition mutations (audited, but `status` unchanged)

These methods on `Booking` write a `BookingEvent` row (with `from_status == to_status`) for audit but do not advance the state machine. They re-validate availability and/or re-run the pricing engine as appropriate.

| Method | Allowed from | Behaviour |
|---|---|---|
| `modify_dates(date_from, date_to, *, actor, reason)` | AWAITING_DEPOSIT, DEPOSIT_PAID, AWAITING_BALANCE, BALANCE_PAID | Acquires a short-lived `BookingHold` on the new range, asserts availability (must respect change-over rule), re-runs `PricingEngine.quote(...)` against the new range, replaces `pricing_snapshot`, recomputes `rental_price` / `balance_due` / `balance_due_at`. Releases the prior date hold. Writes a `BookingEvent` with `meta={"from": [date_from, date_to], "to": [...], "from_snapshot": {...}, "to_snapshot": {...}}`. Refused once `status == CHECKED_IN` (use `cancel` + re-book instead) or from terminal states. |
| `modify_guests(adults, children, infants, *, actor, reason)` | every state up to and including BALANCE_PAID (not from CHECKED_IN or terminal states) | Updates party-size fields; re-runs `PricingEngine.quote(...)` because party size can resolve to a different `RateRule` (occupancy band) and re-derives `rental_price` / `balance_due`. Writes a `BookingEvent` with `meta={"from": {...}, "to": {...}, "from_snapshot": {...}, "to_snapshot": {...}}`. |
| `archive(*, actor)` | Terminal states only: `CHECKED_OUT`, `CANCELLED`, `EXPIRED`, `DECLINED` | Sets `is_archived = True`, `archived_at = now()`. Booking disappears from the default `/bookings` list (operator filter) and surfaces under `/bookings/archived`. Writes a `BookingEvent` with `meta={"archived": true}`. Archive is an explicit, queryable flag — not a hidden row. |
| `restore(*, actor)` | `is_archived == True` (any underlying `status`) | Sets `is_archived = False`, clears `archived_at`. Booking returns to the main list at its existing terminal `status`. Writes a `BookingEvent` with `meta={"archived": false}`. |
| `send_confirmation_email(*, actor)` | any non-terminal active state once a confirmation has been issued at least once | Idempotent re-send of the latest confirmation email. No state mutation; writes a row to the comms log (when the future `comms` app lands) and a `BookingEvent` with `meta={"resent_confirmation": true}` for audit. Matches the legacy "Resend Booking Summary" button on `BookingInfo.razor`. |

### Active states (used by DB exclude constraint)

`AWAITING_DEPOSIT`, `DEPOSIT_PAID`, `AWAITING_BALANCE`, `BALANCE_PAID`, `CHECKED_IN`. These rows participate in the no-overlap rule. The exclude constraint is partial: `WHERE status IN (...)`.

`PENDING_OWNER_APPROVAL` and `DRAFT` do not block the DB constraint but are protected by their `BookingHold` (which has its own exclude constraint).

Note the availability **service** is broader than the DB constraint: `Booking.objects.occupying` treats any non-terminal booking as occupying the range, including resting `DRAFT` rows. The legacy migration rests imported reservations in `DRAFT` (`data_migration.loaders.bookings`) precisely to bypass the EXCLUDE constraint so historical overlaps can coexist — those rows still show as unavailable on the calendar and in catalogue search. See the `occupying` docstring in `reservations/models/booking.py` for the deliberate occupies-vs-blocks asymmetry.

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

## Stay-option search (`POST /quotations:search-options`, 2026-06 quote-builder rework)

The quote builder's search lives in the **reservations** layer (`StayOptionsService` + `reservations/views/quote_options.py`) because it combines the pricing engine with the availability predicates, which pricing may not import. For each requested property it prices one stay and reports `stay_options`: the changeover-to-changeover blocks (whole-week multiples nearest the requested length, arriving on the property's changeover weekday) that fit the window `requested ± flex_days`. Only the default block (closest to the requested arrival) is priced; the frontend reprices alternatives through the same endpoint with `flex_days=0`.

Per-block `is_available` flags come from **one batched fetch** of `Booking.objects.occupying` + `BookingHold.live_overlapping` across all requested properties, with in-memory half-open `[from, to)` overlap tests — so a block arriving the day another stay departs is available (back-to-back changeover). The flags are **advisory snapshots only** — quoting never blocks availability (holds are a manual per-line operator action). The transactional `HoldUnavailable` guard fires when the operator holds the line (`QuotationService.hold_line`) or converts it to a booking.

## Owner block / maintenance

Modelled as `BookingHold` rows with `reason=OWNER_BLOCK` or `MAINTENANCE`, no `expires_at` (set to far future or special sentinel; or make `expires_at` nullable for these reasons specifically — choose at implementation time). They participate in the same `EXCLUDE` constraint, so no special-case query. `STOP_SALE` joins these as a persistent, no-auto-expiry block reason (the `expire_holds` task only touches rows with `expires_at < now()`); it is the model backing the operator-facing "Stop Sale" `CellStatus` — owner using the villa, blocked, not for rent, or booked by a competitor (see `10-decisions.md` "Stop Sale in the availability display vocabulary").

## Out of scope (future)

- **iCal feed ingest from owners.** ~30 villas already publish public iCal feeds that the legacy team mirrors manually through Outlook; pulling them in writes `BookingHold(reason=OWNER_BLOCK, …)` rows directly onto the availability surface with no change to the model above. Post-MVP force-multiplier that has **since been built** (engine + conflict alert + in-app `OwnerBlockUpdate` awareness feed; the per-poll awareness *digest email* deferred in favour of that feed). Full spec, verified assumptions, and resolution: **`todo/done/gap-011-ical-feed-ingest.md`** (✅ resolved 2026-06-22).

## Dropped from legacy

- `VillaAvailability` daily-row table — replaced by range queries over `Booking` and `BookingHold`.
- Status codes 10/40/60/70 — replaced by the BookingStatus enum and BookingHold semantics.
- The 7-day auto-release stored proc — replaced by `expire_holds` Celery task using `expires_at`.
- `UpdateAvailabilty` stored proc — never needed; the exclude constraint and transition methods handle it.
