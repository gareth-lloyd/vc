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
