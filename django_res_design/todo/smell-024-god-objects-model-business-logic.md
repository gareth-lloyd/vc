# SMELL-024 — God objects: business logic on the `Booking` model and in views; oversized engine/stay-options methods

- **Severity:** 🟡 Smell
- **Source:** the 2026-07-02 backend complexity audit (oversized modules / logic in the wrong layer)
- **Files:** `reservations/models/booking.py` (913 lines — esp. `_rerun_pricing`
  `:500–523`, `modify_dates`/`modify_guests` `:541–669`, confirmation-email
  dispatch `:699–725`), `reservations/views/quotation.py:405–430`
  (`perform_update`), `:261–331` (`convert`), `:222–259` (`duplicate`),
  `pricing/services/engine.py:86–374` (`PricingEngine.quote`, ~270 lines +
  52-line inline breakdown dict `:302–354`),
  `reservations/services/stay_options.py` (554 lines;
  Q-013 error-shaping duplicated `:223–238,326–353,492–509`)

## Problem

Business logic has accreted in layers CLAUDE.md reserves for other roles:

- **`Booking` is a god object.** Beyond field definitions it owns availability
  querysets, reference derivation, 11 transition methods, **repricing that
  imports the pricing engine** (`_rerun_pricing`), payment-schedule resync
  signalling, full `modify_dates`/`modify_guests` reprice+persist+event+resync
  flows, and operator confirmation-email dispatch — logic the project's own
  layering rule says lives in services. `BookingService` is a thin ~180-line
  creator while the heavy modify/reprice logic sits on the model where it
  can't be composed or tested without a full ORM instance.
- **Orchestration in the quotation viewset.** `perform_update`
  (`quotation.py:405–430`) hand-codes save-before-reprice ordering, currency
  re-defaulting, pin/unpin, reprice, then hold relocation; `convert`
  (`:261–331`) runs accept+booking-create with inline race recovery;
  `duplicate` (`:222–259`) deep-clones header+lines inline — all recipes the
  vertical-layering contract puts in `services/`. (Overlaps SMELL-009's clone
  finding.)
- **Oversized methods.** `PricingEngine.quote` is one ~270-line method ending
  in a 52-line breakdown dict that interleaves money, provenance, and a UI
  badge; `StayOptionsService` (554 lines) duplicates the Q-013
  error-to-shape conversion in three places. (The genuinely tricky money math —
  `_derive_commission_and_tax`, `_apply_discounts` — is *already* extracted and
  unit-testable; the tangle is the assembly around it.)

## Why it bites

These are maintainability, not correctness — but each new rule adds a branch
to an already-long method or another responsibility to the model, and logic on
the model / in views can't be reused or tested in isolation, so the next caller
re-implements it slightly differently (exactly how SMELL-009's three clones
happened).

## Proposed fix

Incremental, behaviour-preserving extractions — take them the next time each
app is touched, not as one big-bang:

- Move `modify_dates`/`modify_guests`/`_rerun_pricing`/reference derivation off
  `Booking` into `BookingService`; leave the model = fields + the transition
  primitive (see BUG-015 / Q-024).
- Push `perform_update`'s reprice/hold recipe, `convert`, and `duplicate` into
  `QuotationService` (folds into SMELL-009).
- Split `PricingEngine.quote` into `_price_nights(...)` and
  `_build_breakdown(...)`; leave `quote` a thin orchestrator. Centralise the
  Q-013 error-shaping in `stay_options` into one helper.

## Acceptance

- No pricing-engine import or multi-step reprice/hold recipe remains in a view
  or on the `Booking` model; `BookingService`/`QuotationService` own them.
- `PricingEngine.quote` delegates night-pricing and breakdown assembly to named
  helpers; the Q-013 shaping has a single implementation.
- Existing behaviour tests unchanged (pure refactor).

## Dependencies

Overlaps SMELL-009 (clone endpoints → services), SMELL-012 (module-structure
drift), SMELL-008 (service-layer contract). Sequencing tied to Q-024 /
BUG-015 (the `Booking` transition/reprice extraction shares that seam).
