# GAP-021 — Per-entity "History" tab in the SPA (audit-log surface)

- **Severity:** Gap (designed-but-unbuilt surface)
- **Source:** the 2026-06-11 audit-logging review; Q-014 follow-up list
- **Files:** `core/views.py:68–103` (`AuditLogViewSet`),
  `core/serializers/audit_log.py`, frontend booking/property/finance
  detail screens

## Problem

The backend read surface already exists and is filterable by entity:
`GET /api/v1/audit-log?entity_type=reservations.booking&entity_id=<pk>`
(plus `actor`, `created_after/before`, `action`). Nothing in the SPA
consumes it — audit data is write-only from the operator's point of view,
which halves its value (the trail exists but answering "who changed this
deposit percentage?" requires a shell).

## Proposed fix

- A "History" tab (or drawer) on detail screens, starting where the
  questions actually arise: **PropertyFinance / GroupFinance** (commission,
  bank, deposit terms), then Booking, then Property. Render
  `created_at · actor_email · field: old → new` rows from `field_diffs`;
  `__deleted__` rows render as a deletion banner.
- Domain event timelines (`BookingEvent`, `EnquiryEvent`) already serve the
  activity-feed use case — this tab is the *field-diff* complement, not a
  replacement. Don't merge the two streams in v1; link between tabs if both
  exist on a screen.
- Exposure is gated on **Q-014's** second question (operator vs
  admin-only). Current backend permission is `IsStaffRoleAdmin`; if Q-014
  lands on operator-visible, the viewset needs a scoped-down permission +
  possibly per-entity-type allowlist.
- Backend nit to pick up alongside: the `action` filter uses
  `field_diffs__has_key` with no GIN index (flagged in the code comment at
  `core/views.py:96`). Add `GinIndex(fields=["field_diffs"])` only if/when
  this filter is actually used by the UI.

## Acceptance

- History tab on PropertyFinance shows a just-made commission edit with
  actor and old → new values.
- Pagination + date filtering work against a seeded history.
- Permission behaviour matches the Q-014 decision.

## Dependencies

- **Blocked by Q-014** (exposure decision). Retention half of Q-014 does
  not block.
- BUG-012 should land first so the UI never displays PII that a scrub
  should have removed.
