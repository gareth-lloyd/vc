> **✅ RESOLVED (2026-06-15)** — Problem: What is the scope of channel sync? Fix: Decided: channel sync is out of v1.
>
> _Original ticket preserved below for context._

# Q-003 — Channel sync scope (Airbnb / Booking.com / VRBO)

- **Status:** ✅ **RESOLVED** (2026-05-27 critique) — `10-decisions.md`
  Deferred table: "Channel-manager integrations (Booking.com, Vrbo) —
  Out of v1; would land as new `integrations.SyncClient` subclasses."
  v1 ships with zero external channels.
- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 3
- **Blocks:** `04-rest-api-surface.md` §2.25, the integrations app
  channel adapters

## Question

`04-rest-api-surface.md` §2.25 lists Airbnb / Booking.com / VRBO.
Which channels are in scope for **v1** vs **v2**?

Each channel is meaningful engineering effort (channel-specific availability
sync, rate sync, booking ingestion, cancellation propagation). Cutting
scope here saves large blocks of work.

## Follow-up once answered

- Mark v2-only channels explicitly in `04-rest-api-surface.md` so they
  don't appear in implementation-tracking work.
- Adapter scaffolding only for the v1 set.
