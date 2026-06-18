# GAP-037 — Services as a separate entity + tab, split from season inclusions

- **Severity:** Gap (designed-but-unbuilt; model + UX decision).
- **Source:** 2026-06-17 owner Loom (pricing walkthrough, 0:58–1:30).
- **Files:**
  - `django_res/pricing/models/rate.py` (`RatePlan.inclusion` free text)
  - `django_res/pricing/models/extra.py` (`Extra`, date-banded paid add-on)
  - `django_res/properties/models/features.py`
    (`Feature.service_type = included_service`)
  - `frontend/src/features/properties/tabs/PricingTab.tsx`,
    `frontend/src/features/properties/tabConfig.ts`
  - design: `django_res_design/04-pricing.md`, `02-properties.md`

## Problem

Service inclusions today are a free-text `RatePlan.inclusion` string nested
inside a rate plan's date band. The owner wants **services as a first-class
concept**: each service has its **own date range + descriptive copy** ("date
range, and some copy for the service inclusion"), independent of rates, and
surfaced on **their own tab next to Pricing** rather than buried inside a
season. Quote: "these could just be known as services… which frankly could have
their own tab next to pricing."

**Duplication risk to resolve up front:** there are already *three* inclusion
concepts in the system — `RatePlan.inclusion` (free text), `Extra` (date-banded
paid add-on), and `Feature.service_type = included_service`. This ticket's job
is to **reconcile into one home for services, not add a fourth.**

## Proposed direction

Evaluate three options and recommend one:

- **(a) Reuse `Feature(service_type=included_service)`** surfaced on a new
  **Services** tab — cheapest, no new model. Caveat: `Feature` has no date
  range, so confirm whether per-service date-banding is actually required.
- **(b) Extend `Extra`** (already date-banded via `applies_from`/`applies_to`)
  to carry non-priced informational services.
- **(c) New lightweight `PropertyService` model** (property FK, name, copy,
  `applies_from`/`applies_to`, `sort_order`, `is_active`) — only if neither
  existing model fits.

UX in all cases: split the Pricing tab so seasons/rates stay under **Pricing**
and inclusions move to a **Services** tab (`PricingTab.tsx`, `tabConfig.ts`);
migrate existing free-text `RatePlan.inclusion` content into the chosen home.

## Open questions

1. Are services priced or purely informational? (Drives reuse of `Extra` vs a
   new informational model.)
2. Is per-service date-banding actually needed, or is the rate plan's date band
   sufficient?
3. Do services feed guest-facing comms? (Relates to GAP-018.)
4. One global services list per property, or per-season overrides?

## Acceptance

- Model/UX decision recorded in `10-decisions.md`.
- Spec updated (`04-pricing.md` / `02-properties.md`); the new tab structure
  noted and `RatePlan.inclusion`'s fate (migrate / deprecate) stated.

## Dependencies

- Q-022 (season inclusions move out of the rate plan; tiers stay on bands).
- GAP-018 (itemised guest-facing copy) — if services surface to guests.
- Overlap with `Feature.service_type` and `Extra` — must not create a fourth
  inclusion concept.
