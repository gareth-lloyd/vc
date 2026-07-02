# GAP-017 — data-migration loader for legacy `VillaBookingDetails`

> **✅ RESOLVED (2026-07-02)** — `BookingChargeItemLoader`
> (`django_res/data_migration/loaders/bookings.py`) ports the rows with
> convert-or-flag currency handling (`FxConverter` pinned at
> `as_of=booking.date_from`, no-rate rows land in `LoadReport.errors`),
> payment-resync suppression around the load (the receiver disconnect the
> ticket asked for — note the "loaders already run with signal discipline"
> claim below was wrong; this is the package's first suppression), a removal
> sweep for vanished/zero rows, and a `reconcile_legacy` check
> (`expected_gap=0` placeholder, recalibrate at dry-run). The double-count
> worry resolved without heuristics: legacy's displayed total was
> `RentalPrice + Σ details`, the exact shape of the new
> `balance_due + Σ charge_items`, so verbatim same-currency porting
> reproduces legacy totals by construction. Playbook:
> `data_migration/CUTOVER.md` §4g.

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
