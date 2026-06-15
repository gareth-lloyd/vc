# FG-011 — `Booking.adjustment` recompute rides signals; bulk writes desync it

- **Severity:** 🟠 Footgun
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `reservations/signals.py:121–141`

## Problem

The `Booking.adjustment` denorm is recomputed only via signal receivers on
`BookingConciergeItem` save/delete:

```python
def _concierge_item_changed(sender: type, instance: Any, **_: Any) -> None:
    _recompute_booking_adjustment(instance.booking_id)
```

Queryset `.update()`, `bulk_create`, and `bulk_update` on
`BookingConciergeItem` fire no signals, so any bulk write (a future loader,
an admin action, a batch price change) silently desyncs the denorm. This is
the same bug class as BUG-007's `save()`-override reference allocator —
"works until the first bulk path".

## Proposed fix

- Add a service-layer recompute entry point (a `ConciergeService` write API
  that always calls `_recompute_booking_adjustment` after its writes) and
  route bulk mutations through it; and/or
- a periodic reconciler task that compares `Booking.adjustment` against the
  aggregate and corrects drift with a summary log line
  (`booking.adjustment_reconciled count=…`).

KISS: the service entry point is the cheap, primary fix; the reconciler is
optional belt-and-braces.

## Acceptance

- Test: a queryset `.update()` on concierge items followed by the
  service-level recompute (or the reconciler) leaves `Booking.adjustment`
  correct.
- A comment on the signal receivers names the bulk-path limitation.

## Dependencies

None.

## Resolution (2026-06-15)

✅ Fixed. The recompute is now a service entry point rather than a private
signal helper:

- `ConciergeService.recompute_adjustment(booking_id)` — re-derives
  `Booking.adjustment` from the booking's non-cancelled concierge lines (the
  logic moved out of `signals._recompute_booking_adjustment`, which is gone).
- `ConciergeService.recompute_for_bookings(booking_ids)` — batch entry point
  for bulk mutations spanning multiple bookings (dedupes ids).
- The `_concierge_item_changed` signal receiver now delegates to
  `recompute_adjustment` and carries a comment naming the bulk-path
  limitation: any `queryset.update()` / `bulk_create` / `bulk_update` on
  `BookingConciergeItem` must call the service explicitly because no signal
  fires for it.

KISS / matching FG-016: an explicit call at the bulk site, not a new
bulk-signal framework. No periodic reconciler was added — there are currently
no production bulk concierge write paths to drift against; the service entry
point is the cheap primary fix the ticket prescribes, and the reconciler is
flagged optional. If bulk concierge writers proliferate, revisit.

Tests (`reservations/tests/test_concierge.py`):
`test_bulk_update_desyncs_until_service_recompute` (a `.update()` leaves the
denorm stale, then the service recompute corrects it) and
`test_recompute_for_bookings_handles_multiple` (a `bulk_create` corrected via
the batch entry point). Signal-driven paths behave identically (existing tests
unchanged). No migration (denorm column already exists).
