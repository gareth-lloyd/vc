# GAP-017 — data-migration loader for legacy `VillaBookingDetails`

- **Severity:** Gap
- **Source:** booking-charge-items work (2026-06-10)
- **Files:** `django_res/data_migration/` (new loader),
  `django_res/reservations/models/charge_item.py`

## Problem

`BookingChargeItem` carries the importable-model `legacy_id` column, but no
loader ports the legacy `VillaBookingDetails` rows (BookingId, CurrencyId,
Price, Notes). Until it exists, imported bookings lose their manual price
lines — and their `balance_due` (loaded from legacy `RentalPrice`, which
already includes extras in some flows) needs reconciling against
`Σ charge lines` so totals don't double-count.

## Constraints the loader must own

- **Currency conversion/flagging:** the live Σ in the API assumes
  single-currency rows; `ChargeItemService` validates this but loaders bypass
  the service. Rows whose `CurrencyId` differs from the booking currency must
  be converted (FxRate) or flagged for manual review — never written verbatim.
- **No schedule resync on import:** loading historical rows must not resize
  live payment schedules. Either disconnect the
  `payments.resync_on_booking_total_changed` receiver for the load (the
  loaders already run with signal discipline — see CUTOVER.md) or assert the
  imported bookings hold no PENDING schedule rows.
- **Idempotency:** keyed on `legacy_id`, like every other loader.
- Read `django_res/data_migration/CUTOVER.md` before building.
