# Q-022 — Seasons defined by rental rates, not services

- **Severity:** Question (modelling decision; reporting impact)
- **Source:** 2026-06-11 email thread (Nick Cookson + Bryony Moger);
  2026-06-17 owner Loom (pricing walkthrough, 1:30–2:40)
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

## Owner answer (2026-06-17 Loom)

The owner resolved Q2/Q3: a **season is a named tier/category** — he listed
*top peak season*, *peak / high season*, *shoulder season* — that an operator
**applies over week-priced rate bands** by "bunching certain dates or certain
weeks together" and labelling the group. The season is therefore **a category
attached to the bands, not the `RatePlan` itself** ("we want to be able to put
prices per week, and then be able to categorize certain sections of the pricing
calendar as high season / peak").

Its primary driver is **cross-villa reporting** ("peak-season bookings up X%,
mid down X%") and pricing decisions ("20% reduction peak→high") — which is why a
free-text label is insufficient: it must be a controlled tier that aggregates
across villas despite each villa's bespoke date ranges. Q1 (cross-villa
standardisation, Bryony's concern) remains the one open question.

## Open questions

1. How are season tiers (top-peak/peak/high/shoulder/low) **standardised for
   cross-villa reporting** when each villa defines its own date ranges?
   (Bryony's concern — still open.)
2. ~~Is "season" a named/categorised band, or just the rate bands themselves?~~
   **Answered:** a named tier/category applied over rate bands.
3. ~~Is the season the rate plan, the band, or a category attached to either?~~
   **Answered:** a category attached to the bands.

## Proposed fix / direction

Introduce a controlled `season_tier` enum (curated set — confirm exact list
with product; owner named TOP_PEAK / PEAK·HIGH / SHOULDER, plus a LOW for
year-round flat villas) attached at the **rate-band level** (`RateRule`, or
`RateCard` if a card cleanly equals one tier), so reporting aggregates on the
tier while each villa keeps its own dates. Note that the tier must **copy with
the base band** on carry-over (Q-018), not with any in-season reduction. Leave
the cross-villa reporting standardisation (open question 1) for the reporting
design.

## Acceptance

- Decision recorded in `10-decisions.md`.
- Relevant pricing design doc updated (`04-pricing.md` / `02-properties.md`).
- Model implications scoped (`season_tier` placement on band vs card).

## Dependencies

- Relates to GAP-025 / Q-018 (rate-band entry; tier copies with the base band
  on carry-over).
- GAP-037 (services split): the **inclusions** half of the legacy "season"
  moves to a Services concept; this ticket keeps the **rate-tier** half.
- The pricing model (`RatePlan` / `RateCard` / `RateRule`).
