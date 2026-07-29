# Q-022 — Seasons defined by rental rates, not services

- **Severity:** Question (modelling decision; reporting impact)
- **Source:** 2026-06-11 email thread (Nick Cookson + Bryony Moger);
  2026-06-17 owner Loom (pricing walkthrough, 1:30–2:40)
- **Files:** `django_res_design/04-pricing.md` (rewritten as-built by Q-018;
  model now `Property → RatePlan → RatePeriod → RateBand` — see the
  2026-07-29 note below), `django_res_design/02-properties.md`,
  `django_res/pricing/models/rate.py` (`RatePeriod` — candidate tier home)

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

> **2026-07-29 rewrite (model drift):** this section originally targeted the
> pre-GAP-056 `RatePlan`/`RateCard`/`RateRule` model — `RateCard` was dropped
> and `RateRule` renamed `RateBand`; the current model is
> `Property → RatePlan → RatePeriod → RateBand` (GAP-056 / SMELL-019). The
> mechanics below are restated against it; the owner answer is unchanged.

Introduce a controlled `season_tier` enum (curated set — confirm exact list
with product; owner named TOP_PEAK / PEAK·HIGH / SHOULDER, plus a LOW for
year-round flat villas). The natural home in the current model is
**`RatePeriod`** — a period is already exactly the owner's "bunch of weeks
with a label" (named, date-windowed, per-villa), so the tier is a second,
controlled label alongside `RatePeriod.name` (GAP-059) rather than a per-band
attribute; reporting aggregates on the tier while each villa keeps its own
dates. Note that the tier must **copy with the base** on carry-over (Q-018 —
carry-over already copies the base, not any in-season reduction), and that
[SPEC-001](spec-001-rateplan-date-authority-regime-bucket.md) explores making
`RatePeriod` the sole date authority — a tier-on-period decision here should
be made with that exploration in view (it strengthens the period's claim to
be the season-shaped object). Leave the cross-villa reporting standardisation
(open question 1) for the reporting design.

## Acceptance

- Decision recorded in `10-decisions.md`.
- Relevant pricing design doc updated (`04-pricing.md` / `02-properties.md`).
- Model implications scoped (`season_tier` placement on `RatePeriod` vs
  `RateBand`).

## Dependencies

- Relates to GAP-025 / Q-018 (rate entry; tier copies with the base on
  carry-over).
- GAP-037 (services split): the **inclusions** half of the legacy "season"
  moves to a Services concept; this ticket keeps the **rate-tier** half.
- The pricing model (`Property → RatePlan → RatePeriod → RateBand`, GAP-056);
  [SPEC-001](spec-001-rateplan-date-authority-regime-bucket.md) (period as
  date authority — structural counterpart to this question).
