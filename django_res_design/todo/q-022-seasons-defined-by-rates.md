# Q-022 — Seasons defined by rental rates, not services

- **Severity:** Question (modelling decision; reporting impact)
- **Source:** 2026-06-11 email thread (Nick Cookson + Bryony Moger)
- **Files:** `django_res_design/04-pricing.md` (`RatePlan` "season",
  `RateRule` bands), `django_res_design/02-properties.md`

## Problem

Nick proposed that **seasons be defined by rental rates** rather than by
services (the legacy basis). His reasoning is twofold: it reads better for
**reporting** (e.g. "peak-season bookings up X%, mid down X%") and it maps
naturally to **pricing** decisions ("20% reduction from peak to high").

Bryony agreed seasons should be defined by the villa's rental rates, **but**
flagged that each villa has a **different seasonal structure** — some are
flat year-round, some treat peak as Jul/Aug, and some use bespoke ranges
like 8 Jul–22 Aug. Her concern: this per-villa variability complicates
**standardised reporting** across peak/shoulder/low, because there is no
single calendar-aligned definition of a "season" to aggregate on.

The same email also touched on **Villa Groups** being removed — but per the
rebuild that decision was **deferred** (groups stay; see q-021).

## Open questions

1. How are season categories (peak/shoulder/low) **standardised for
   cross-villa reporting** when each villa defines its own date ranges?
2. Is "season" a **named/categorised band** on the rate structure, or just
   the rate bands themselves (an emergent grouping)?
3. How does this relate to the existing `RatePlan` ("season") model and the
   `RateRule` bands — is the season the rate plan, the band, or a category
   attached to either?

## Acceptance

- Decision recorded in `10-decisions.md`.
- Relevant pricing design doc updated (`04-pricing.md` / `02-properties.md`).
- Model implications scoped.

## Dependencies

Relates to GAP-025 / Q-018 (rate-band entry) and the pricing model.
