# `django_res_design/` — Villa Collective design & reference

This directory documents both the **legacy** villa-rental platform
(`../ResSystem/`, .NET 7 / Blazor / SQL Server) and the **rebuild** we are
shipping (Django REST API + React SPA). It has drifted from the code over time,
so it is organised into three tiers by *what you can trust each for*:

| Tier | Directory | What it is | Trust it for |
|---|---|---|---|
| **1 — Legacy** | [`legacy/`](legacy/) | The old .NET system's as-built behaviour, extracted from `../ResSystem/`. **Frozen.** | "What did the old system actually do?" |
| **2 — Design** | [`design/`](design/) | The design of the system we're building. A few living docs + code are canonical; the field-level specs are frozen design-time rationale. | "Why is the rebuild shaped this way?" — and, via its canonical map, "what is the backend today?" |
| **3 — Work queue** | [`todo/`](todo/) | The live ticket system: bugs, gaps, smells, questions, decisions blocking implementation. **The most significant record of what we're building.** | "What's built, broken, or still to do — right now?" |

## Where is the truth?

The design specs were written ahead of the code and drifted (models were
renamed, folded, or dropped: `RateCard` gone, `RateRule` → `RateBand`, the
former `Guest` folded into a unified `accounts.Person`, property `Group`s being
removed). When a spec disagrees with reality, trust this order:

1. **The code in `../django_res/`** — the final authority.
2. **[`design/data-model-overview.md`](design/data-model-overview.md)** — the
   canonical, living as-built map of the backend.
3. **[`todo/INDEX.md`](todo/INDEX.md)** — what's open, and the decisions that
   have been taken.
4. **[`design/decisions.md`](design/decisions.md)** /
   **[`design/departures.md`](design/departures.md)** — why the design is what it
   is, and how it maps to the legacy tables.

Everything under `design/backend/`, `design/product/`, and `design/history/`
carries a **frozen** header — read it for design-time *rationale*, never as a
description of what currently exists.

## The product (unchanged across legacy & rebuild)

A management platform for **luxury whole-property villa rentals**:

- A curated portfolio of villas across countries/regions — rich descriptions,
  image galleries, features, owner/agent contacts.
- An **Enquiry → Quotation → Booking → Check-in → Check-out** lifecycle, sourced
  from website forms and direct agent input.
- Sophisticated pricing: per-villa rate periods, occupancy bands, taxes, agent
  commissions, discounts, POA, multi-currency.
- Owner-confirmed bookings (manual approval), a 3-tier payment schedule (deposit
  / balance / security deposit, via Flywire), concierge add-ons, and Zoho CRM
  integration.

## Reading order

- **New to the project?** [`design/data-model-overview.md`](design/data-model-overview.md)
  (what the backend is) → [`design/departures.md`](design/departures.md) (how it
  differs from the legacy system) → [`todo/INDEX.md`](todo/INDEX.md) (what's left).
- **Reproducing a legacy behaviour?** Start in [`legacy/`](legacy/) — its
  [`README.md`](legacy/README.md) indexes the workflow domains, and
  [`legacy/quote-enquiry-reference.md`](legacy/quote-enquiry-reference.md) is the
  corrected reference for the pre-deletion quote/enquiry UI.
- **Doing product/UX or API work?** The frozen [`design/product/`](design/product/)
  specs (frontend design, workflows, REST surface) give the design-time intent —
  always cross-checked against the code and `todo/`.
- **Picking up implementation?** Work from [`todo/`](todo/); consult the frozen
  [`design/backend/`](design/backend/) specs for field-level rationale on the
  area you're touching.

## Legacy data carry-over

Legacy data is ported by the loaders in `../django_res/data_migration/`
(`./manage.py loadlegacy --all`, `reconcile_legacy`, `merge_country`; full
playbook in `../django_res/data_migration/CUTOVER.md`).
[`design/departures.md`](design/departures.md) is the table-by-table mapping
that migration follows.
