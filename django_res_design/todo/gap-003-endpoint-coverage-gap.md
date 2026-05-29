# GAP-003 — Endpoint coverage gap vs. designed surface

- **Status:** ❌ **DROPPED** (2026-05-27 critique) — framing only, not
  actionable as a single ticket. The ticket itself acknowledges this
  ("don't tackle this as a single ticket"). Rely on journey-driven
  per-area tickets instead.
- **Severity:** Gap (tracking)
- **Source:** `product-design/04-rest-api-surface.md`
- **Files:** all `*/urls.py`

## Problem

The design lists ~357 endpoints across the v1 surface. A `grep -c`
across the implemented `urls.py` files shows a much smaller subset
landed (accounts, properties, pricing, reservations, payments). Two
apps (comms, integrations) have empty URL files (see
[GAP-001](gap-001-comms-empty-url-surface.md),
[GAP-002](gap-002-integrations-empty-url-surface.md)).

## Approach

Don't tackle this as a single ticket — track per-area instead. The
implementation order should follow the canonical journeys in
`06-verification.md` §1:

1. **New lead → confirmed booking** — most of this surface exists.
2. **Modification under pressure** — booking modify endpoints exist;
   verify the audit + notification side-effects do too.
3. **Cancellation with refund** — refund endpoints exist; cancellation
   policy still blocked on [Q-001](q-001-cancellation-policy-thresholds.md).
4. **Owner approval cycle** — owner portal scope is large; needs its
   own breakdown.
5. **Portfolio season setup** — admin bulk endpoints largely TBD.

## Follow-up

Once the open questions land, break each journey into a small set of
endpoint tickets and replace this aggregator. For now it's a reminder
that the design covers significantly more surface than is built.

## Dependencies

Most product questions in `q-*` tickets.
