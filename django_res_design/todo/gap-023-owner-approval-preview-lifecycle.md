# GAP-023 — `live_offline` replacement: owner approval, preview link, sales-facing badges

- **Severity:** Gap (legacy-parity regression + workflow safety) — **DEFERRED post-v1 per 2026-06-11 email**
- **Source:** 2026-06-11 new-villa setup transcript review
- **Files:** `properties/models/property.py` (status enum),
  `django_res_design/02-properties.md` (reconciliation issue #23),
  `pricing/models/rate.py` (`RateRule.is_approved`),
  `frontend/src/features/properties/tabs/SettingsTab.tsx` (LifecycleSection),
  quote-builder property search/result surfaces

## Problem

Legacy has four statuses (`live_online`, `live_offline`, `pending`,
`archive`). The new design collapsed `live_offline` into
ARCHIVED + `PropertySettings.availability_default=UNAVAILABLE`
(02-properties.md #23). That covers "temporarily not bookable" but **not
what the loader actually uses `live_offline` for**:

1. **Owner preview before publication** — she clicks "view on website" and
   sends the link to the owner to check and approve the listing.
2. **Internally offerable but not public** — while awaiting approval, the
   sales team can (and should) still pick the villa up for client offers.

Her stated unease is not that sales can see unapproved villas — it's that
**nobody can tell it's unapproved**. Unconfirmed rates have the same
problem: `RateRule.is_approved` exists in the backend (bulk imports land
`False`) but has no UI toggle and is invisible in the quote builder.

## Decision (2026-06-11 email)

**DEFERRED.** Nick (owner) decided owner approval is "best to introduce
further down the line." v1 ships **no approval gating**: sales offer villas
freely, there is no "awaiting approval" hold, and no badges are built now.
Bryony noted that offerable-while-awaiting is fine, and that a new enquiry
can usefully push the owner to respond faster. The audit-trail-on-sign-off
idea is a later Zoho/Res automation, not v1.

The design below is retained as the **eventual** shape for when this is
picked up; it is the future target, not current scope.

## Proposed fix (future target — not current scope)

When this is eventually built, keep the three-state enum and add an
orthogonal approval axis instead of a fourth status:

- `Property.owner_approved_at` (nullable timestamp; cleared on material
  content edits is a follow-up question — start with manual set/clear).
- Shareable preview capability link for DRAFT/unapproved properties
  (token URL, same pattern as other capability URLs in the codebase),
  replacing legacy "view on website" for offline villas.
- Badges, not hiding: quote builder / property search show
  "owner approval pending" and "unconfirmed rates" markers on affected
  properties so sales offer them knowingly.
- Expose `RateRule.is_approved` (read + toggle) in the PricingTab.

## Acceptance (future target — not current scope)

- Approval state settable from the property UI and visible in list/detail.
- Preview link works for a DRAFT property without staff auth.
- Quote builder rows show both badges where applicable; verified with a
  seeded unapproved property + unapproved rate rules.
- `02-properties.md` #23 amended to document the approval axis.

## Dependencies

Distinct from Q-002 (booking owner-approval SLA) — this is listing/content
approval. Pairs with GAP-025/Q-018 on the rates side.
