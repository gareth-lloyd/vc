# FG-017 — Audit-coverage second tier: BookingHold, Property, unaudited property-child hard deletes

- **Severity:** 🟠 Footgun
- **Source:** the 2026-06-11 audit-logging review (sibling of FG-014)
- **Files:** `reservations/apps.py`, `properties/apps.py`,
  `core/tests/test_audit_registry.py`, `properties/views/` (Destroy views)

## Problem

FG-014 covers the money/PII tier (SecurityDeposit, Enquiry, Quotation).
The review found a second tier of untracked surfaces — operationally
significant, lower stakes than FG-014:

- **`reservations.BookingHold`** — availability-blocking lifecycle
  (ACTIVE → RELEASED via `HoldService.place/move/release`). No trail of
  who placed/released a hold; affects inventory-dispute reconstruction.
  Related: BUG-005 (stale holds) — an audit trail would have made that
  diagnosis trivial.
- **`properties.Property`** — the master record (name, operational flags)
  is untracked while its finance/feed children are. Property metadata edits
  by staff leave no trail.
- **Unaudited hard deletes** of property children via Destroy views:
  `Room`, `PropertyImage`, `PropertyNearbyPlace`, `ChangeOverRule`,
  `PropertyContactAssignment`. A deleted room or contact-assignment
  vanishes without record of who or when. (Pricing-model deletes —
  RateRule/RateCard/Extra — are covered once the pricing registrations on
  the review branch land, since `post_delete` fires for any tracked model.)

## Proposed fix

Register with tight field lists per convention:

- `BookingHold`: `fields=["property_id", "quotation_line_id", "status",
  "expires_at", "released_at"]` (adjust to actual columns).
- `Property`: lifecycle/identity fields only (`name`, status/operational
  flags) — *not* the chatty description/content fields.
- Property children: registering each with its few identity fields is
  enough — the goal is the `__deleted__` rows, and `track()` gives delete
  capture for free. If per-edit diffs on these would be noise, that is the
  trade-off to call out; there is no delete-only registration mode today
  (could add `fields=` minimal lists as the pragmatic version).

Update `EXPECTED_TRACKED_MODELS` in the same commit.

## Acceptance

- Registry test pins the new registrations.
- One integration test per group: hold release writes a row; property
  rename writes a row; room delete writes a `__deleted__` row.

## Dependencies

- After FG-014 (same mechanical pattern; FG-014 first — higher stakes).
- More tracked models → Q-014 retention answer matters sooner.
