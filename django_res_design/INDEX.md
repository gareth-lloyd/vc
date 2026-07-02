# Villa Collective — Django REST + React SPA Design Package

Top-level index. This directory contains **two complementary design packages** for rebuilding the .NET / Blazor villa-rental system (`../ResSystem/`) as a Django REST API + React SPA, plus the as-built **workflow specs** in `workflows/` that underpin both.

## Package A — Backend Data Model (top-level files)

A detailed, implementation-ready Django data-model specification. Per-app file layouts, field types, constraints, state machines, services, signals, Celery tasks. **No executable code, but precise enough to implement directly.**

See [`README.md`](./README.md) for the package's own index. For a descriptive
map of the model **as built** in `django_res/` (anchor models, relationships,
cross-cutting patterns), see [`data-model-overview.md`](./data-model-overview.md).
For the People-model cleanup (the unified `accounts.Person` identity — folding
the former Enquiry/Guest/Contact records together — integrity, and
deduplication decisions), see [`people-model-cleanup.md`](./people-model-cleanup.md).

Files: `00-conventions.md`, `01-accounts.md`, `02-properties.md`, `03-finance-config.md`, `04-pricing.md`, `05-reservations.md`, `06-availability.md`, `07-payments.md`, `08-integrations.md`, `09-departures.md`, `10-comms.md`, `10-decisions.md`, `11-milestones.md`, `people-model-cleanup.md`.

**Scope**: Backend models, fields, constraints, services. Database-enforced integrity, state machines, audit, soft-delete. Domain-by-domain (accounts, properties, pricing, reservations, availability, payments, integrations) with a per-table mapping of legacy → new in `09-departures.md`.

## Package B — Product Design (in `product-design/`)

The higher-level product, UX, workflow, and REST-API design. Frontend SPA shell, screens, workflows, REST endpoint inventory, improvements over the original, and verification.

See [`product-design/00-overview.md`](./product-design/00-overview.md) for the entry document.

Files:
- `00-overview.md` — goals, tech stack, repo layout, architecture, reading guide.
- `01-domain-model.md` — entity overview (higher-level than Package A; useful as a fast read).
- `02-frontend-design.md` — React SPA: shell, navigation, screens (with ASCII wireframes), components, state management, auth, accessibility.
- `03-workflows.md` — twenty detailed end-to-end user workflows with state-transition tables, side effects, failure modes, and explicit departures from the original.
- `04-rest-api-surface.md` — REST endpoint inventory. Specification only — no payload schemas.
- `05-improvements-over-original.md` — catalog of deliberate UX/UX departures with rationale.
- `06-verification.md` — how to validate the design, stakeholder review checklist, open questions requiring user decisions before implementation begins.

## Workflow specs (in `workflows/`)

Per-workflow extraction of the legacy system's as-built behaviour — see [`workflows/README.md`](./workflows/README.md) for the domain index. For the legacy quote/enquiry screens specifically, start from [`workflows/legacy-quote-enquiry-reference.md`](./workflows/legacy-quote-enquiry-reference.md) — the corrected reference for what the pre-deletion legacy UI actually did, plus a trust map for the quote/enquiry specs.

## Relationship between the packages

The two packages were authored by different design passes and have **slightly different mental models in places**. Resolve remaining discrepancies during implementation by asking the user and updating both packages.

Specifically:

| Topic | Package A | Package B |
|---|---|---|
| Payment processor | Flywire — **decided** (see `10-decisions.md` and `workflows/11-integrations/flywire-gateway.md`) | Flywire — **decided** (Package B's earlier Stripe placeholder has been replaced throughout) |
| Data model depth | App-by-app, field-level | Aggregate-level overview in `01-domain-model.md` |
| Frontend / UX | Not covered | Detailed in `02-frontend-design.md` |
| User workflows | State transitions noted in models | Full step-by-step in `03-workflows.md` |
| REST API | Implied by model + services | Explicit endpoint inventory in `04-rest-api-surface.md` |
| Departures from legacy | Per-table table in `09-departures.md` | UX-focused summary in `05-improvements-over-original.md` |

## Suggested reading order

1. **For a fast overview**: `product-design/00-overview.md` → `09-departures.md` (the per-table mapping from Package A is the fastest way to see what's changing) → `product-design/02-frontend-design.md` §3 (screen catalog).
2. **For engineering scope/estimation**: `product-design/04-rest-api-surface.md` (count the endpoints) → `README.md` (Package A) → `product-design/03-workflows.md` (the side-effects + state transitions reveal where the real complexity is).
3. **For product/UX sign-off**: `product-design/02-frontend-design.md` §3 → `product-design/03-workflows.md` → `product-design/05-improvements-over-original.md`.
4. **For implementation planning**: Package A in numbered order is the implementation guide; Package B's `04-rest-api-surface.md` is the API surface to expose; Package B's `03-workflows.md` is the acceptance-criteria narrative.

## Open work

`product-design/06-verification.md` lists 15 open questions that should be answered before implementation begins (payment gateway choice, cancellation policy thresholds, owner pre-approval SLA, channel scope for v1, etc.). Resolve these and fold answers back into the relevant docs.

`11-milestones.md` is the **authoritative delivery-phasing layer**: it defines what ships in **Milestone 1** versus what is deferred to **M2+**. When a doc and a milestone scope appear to disagree on whether something is in scope "now," `11-milestones.md` wins. (For example, the narrow reference-scoped guest checkout is Milestone 1 — see `product-design/02-frontend-design.md` §7.5 — while the full post-booking guest portal is deferred to M2+.)
