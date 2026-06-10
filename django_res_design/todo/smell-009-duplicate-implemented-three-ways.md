# SMELL-009 — "Duplicate" is implemented three different ways, none idempotent

- **Severity:** 🟡 Smell
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `properties/services/lifecycle.py:71–95`,
  `pricing/views/rate.py:61–86` (`SeasonDuplicateView`) and `:168–191`
  (`RateCardDuplicateView`), `reservations/views/quotation.py:181–230`

## Problem

Three clone features, three shapes:

- Villa duplicate is a proper service
  (`PropertyLifecycleService.duplicate`, lifecycle.py:73).
- Season and rate-card duplicates are hand-rolled `pk = None` clones inside
  `APIView.post` (e.g. rate.py:64–86 walks plan → cards → rules in the
  view).
- Quotation duplicate is a viewset `@action` with inline clone + hold
  re-placement logic (quotation.py:182–230).

Beyond the inconsistency, none of the clone endpoints has double-click
protection — a double-submitted duplicate silently creates two clones
(`"… (copy)"` names don't collide), violating the project's own
idempotency convention for operator-UI submits.

## Proposed fix

Extract the pricing and quotation clone logic into their apps' service
layers (mirroring `PropertyLifecycleService.duplicate`), each accepting an
optional `idempotency_key` via `core.idempotency`; views become thin
delegations. Behaviour-preserving refactor — the cloning rules themselves
don't change.

## Acceptance

- Clone logic lives in `pricing/services/` and
  `reservations/services/quotations.py`; views contain no `pk = None`
  walks.
- Test per endpoint: a retried duplicate with the same idempotency key
  returns the original clone.

## Dependencies

Related: SMELL-008 (this is part of the contract backfill), FG-010
(idempotency DB backstop shapes the key storage).
