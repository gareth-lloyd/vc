# Design tier — the Villa Collective Django rebuild

This tier holds the design of the system we are **building** (Django REST API +
React SPA) — as distinct from the [`../legacy/`](../legacy/) tier (the old .NET
system, frozen) and [`../todo/`](../todo/) (the live work queue).

## Where is the truth?

The design here was written *ahead of* the code and has drifted. Trust this
table over any single spec:

| You want to know… | Trust this | Status |
|---|---|---|
| What the backend data model **is today** | [`data-model-overview.md`](data-model-overview.md) + the code in `django_res/` | **Living — canonical** |
| Why a design choice was made | [`decisions.md`](decisions.md) | Living |
| What changed vs the legacy system | [`departures.md`](departures.md) | Living |
| Build phasing / sequencing | [`milestones.md`](milestones.md) | Living |
| What's still to build / broken | [`../todo/INDEX.md`](../todo/INDEX.md) | Living — the work queue |
| Field-level backend rationale | [`backend/`](backend/) | **Frozen** design-time spec |
| Product / UX / API-surface rationale | [`product/`](product/) | **Frozen** design-time spec |
| New-system UI mockup analysis | [`mockups/`](mockups/) | Analysis snapshots |
| Fully-superseded rationale (kept for provenance) | [`history/`](history/) | **Frozen** |

**Rule of thumb:** the four living docs at this tier's root
(`data-model-overview`, `decisions`, `departures`, `milestones`) plus `../todo/`
plus the code describe reality. Everything under `backend/`, `product/`, and
`history/` is design-time rationale — each carries a **frozen** header and may
describe things (`RateCard`, `RateRule`, `/guests`, property `Group`s) that were
renamed, folded, or dropped after it was written. Read them for *why*, not *what
is*.

## Contents

- **[`data-model-overview.md`](data-model-overview.md)** — the canonical as-built
  map of the backend: apps, anchor models, relationships, cross-cutting patterns.
  Start here for "how is the backend shaped".
- **[`decisions.md`](decisions.md)** — the living decisions log (numbered,
  keyed by what was decided and why).
- **[`departures.md`](departures.md)** — the single per-legacy-table mapping of
  what the rebuild keeps, changes, or drops vs `../legacy/`.
- **[`milestones.md`](milestones.md)** — delivery phasing.
- **[`backend/`](backend/)** — the numbered field-level backend specs
  (`00-conventions` … `08-integrations`, `comms`). Frozen.
- **[`product/`](product/)** — product design: overview, domain model, frontend
  design, workflows, REST surface, improvements-over-original, verification.
  Frozen.
- **[`mockups/`](mockups/)** — analysis of the new-system UI mockups (new
  res-system, client & owner portals, client emails) against the design.
- **[`history/`](history/)** — rationale that has been fully absorbed elsewhere
  and is retained only for provenance (`people-model-cleanup`,
  `api-schema-reconciliation`).

## Reading order for someone new

1. [`data-model-overview.md`](data-model-overview.md) — what exists.
2. [`departures.md`](departures.md) — how it differs from the legacy system.
3. [`decisions.md`](decisions.md) — why.
4. [`../todo/INDEX.md`](../todo/INDEX.md) — what's left.
5. `backend/` and `product/` only when you need the design-time detail behind a
   specific area — always cross-checked against the code.
