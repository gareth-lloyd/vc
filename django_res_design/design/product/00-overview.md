# 00 — Overview

> **Design-time spec — frozen 2026-07-03.** Rationale for the design as
> conceived; not a live description of the built system. Current truth:
> [`../data-model-overview.md`](../data-model-overview.md) + the code in
> `django_res/` + [`../../todo/INDEX.md`](../../todo/INDEX.md).

## Project goal

Rebuild the existing .NET / Blazor Server villa-rental management system (`ResSystem/`) as a Django REST API backend and a React single-page-application frontend. The new system must feel functionally familiar to current operators while improving the worst friction points in the original.

This `django_res_design/` directory holds the design package: domain map, frontend specification, user workflows, and the REST API endpoint inventory.

## Audience

- Operations team — to confirm the workflows match how they actually work.
- Engineering — to scope, estimate, and build.
- Product / leadership — to sign off on UX departures from the original.
- Property owners — indirectly, via the owner-portal sections.

## Product positioning — high-touch, human-driven sales

Villa Collective is a **high-touch, human-driven** villa-rental business. This is a deliberate product position, not a technical limitation, and it shapes every "should X auto-happen?" decision in this design package.

- **Quotes are agent-crafted.** A salesperson chooses which villas to present, in what order, with what commentary. The system supports the agent; it does not replace them.
- **Clients reply informally.** The norm is an emailed quote followed by an emailed reply ("I want option 2"). The system does not assume the client clicks a button to convert.
- **Conversion to booking is staff-confirmed.** The in-quote "Accept" link is a convenience signal that lights up a staff workflow — it does not auto-create the booking. A human always confirms.
- **Automation lives in admin / back-office workflows.** Hold expiry, payment reminders, security-deposit refunds, comms dispatch — yes. Self-service booking creation off a quote-accept click — no.

This frames every design decision in this package. When a workflow asks "should we just do X automatically?", the answer is shaped by which side of the human-touchpoint line X falls. See `10-decisions.md` "High-touch human-driven sales is the explicit product position".

## Tech stack

**Backend** — Django + Django REST Framework + Postgres. Celery + Redis for async jobs (email send, PDF render, channel sync, Zoho sync, exports). Object storage (S3 or compatible) for images and document assets. **Flywire** is the online card-payment gateway (continuing the legacy integration; see `10-decisions.md`).

**Frontend** — Vite + React 18 + TypeScript. React Router v6 for routing. TanStack Query for server-state. TanStack Table for data grids. React Hook Form + Zod for forms. shadcn/ui (copied components) + Tailwind CSS for design system. Radix primitives for accessible behaviours. Tiptap (ProseMirror) for rich text. date-fns + date-fns-tz for date math and time-zone handling. Zustand for cross-cutting client state.

**External integrations** — Flywire (payments + webhooks). Zoho CRM (leads/quotes/contacts/bookings). Public WordPress site (`WP_Sync_*` push fan-out). Airbnb / Booking.com / VRBO (channel sync, inbound webhooks and outbound updates — future scope). SMTP / SendGrid (email). iCal feeds (signed-URL output).

## High-level architecture

```
                  ┌────────────────┐
                  │  React SPA     │  (Vite build, served as static)
                  │  Owner portal  │
                  └────────┬───────┘
                           │ HTTPS, Bearer tokens
                           ▼
                  ┌────────────────┐         ┌──────────────┐
                  │ Django + DRF   │◀───────▶│  Postgres    │
                  │  /api/v1/      │         └──────────────┘
                  └─┬──────────┬─┬─┘
                    │          │ └──▶ Object storage (images, PDFs)
              Celery│          │
              jobs  ▼          ▼
        ┌──────────────┐  ┌──────────────┐
        │ Email worker │  │ Sync worker  │
        │ PDF render   │  │ Zoho / OTA   │
        │ Exports      │  │ iCal pull    │
        └──────────────┘  └──────────────┘
              ▲                    ▲
              │ webhooks           │ webhooks
              │                    │
        ┌──────────────┐  ┌──────────────────┐
        │   Flywire    │  │ Airbnb/Booking/  │
        │              │  │ VRBO / Zoho CRM  │
        └──────────────┘  └──────────────────┘
```

The SPA is one bundle that switches shell based on the authenticated user's scope: staff users see the operator app under `/`, owners see the owner portal under `/owner/`. Same React code, different layout and route tree.

## Repository layout (proposed)

```
villacollective/
├── backend/
│   ├── config/                # Django project (settings, urls, asgi/wsgi)
│   ├── apps/
│   │   ├── core/              # shared base models, audit log, soft delete
│   │   ├── auth/              # users, roles, 2FA, magic links, sessions
│   │   ├── properties/        # villas, rooms, images, features, content
│   │   ├── pricing/           # seasons, rate cards, occupancy, extras, quote calc
│   │   ├── availability/      # calendar, holds, hold expiry job
│   │   ├── contacts/          # contacts, contact-property mapping
│   │   ├── guests/            # guests/clients (booking-side customers)
│   │   ├── enquiries/         # lead capture
│   │   ├── quotations/        # multi-villa quote builder
│   │   ├── bookings/          # bookings, concierge line items, documents
│   │   ├── payments/          # three payment tracks, refunds, gateway
│   │   ├── communications/    # email templates, email log
│   │   ├── reports/           # occupancy, revenue, owner statements
│   │   ├── exports/           # async export jobs
│   │   ├── integrations/      # flywire, zoho, wordpress, channels, ical
│   │   ├── notifications/     # in-app notifications, preferences
│   │   └── system/            # sites, currencies, countries, regions, config
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/               # shell, router, providers
│   │   ├── features/          # per-feature folders mirroring backend apps
│   │   ├── components/        # shared UI primitives
│   │   ├── lib/               # api client, query keys, hooks
│   │   └── types/             # generated from DRF schema
│   └── package.json
└── django_res_design/         # this design package
```

## Migration strategy

This is a **greenfield rebuild**, not an in-place port. The existing Blazor app and its Microsoft SQL Server database continue running until cutover. The Django app uses Postgres from day one. A separate data-migration script (out of scope for this design package) will read from the legacy schema and write to the new one in a one-shot or coordinated cutover.

Domain semantics, not table structure, are carried over. We deliberately collapse / rename / split entities in the new model where the original schema accreted historical baggage (e.g., separate `VillaWebsitePricing` and `VillaMapping` tables; deeply embedded settings on `VillaMaster`).

## Reading guide

Read in order; each builds on the previous.

1. **`01-domain-model.md`** — entities, relationships, statuses. Required context for the rest.
2. **`02-frontend-design.md`** — app shell, screens, components, state management.
3. **`03-workflows.md`** — twenty detailed end-to-end user workflows.
4. **`04-rest-api-surface.md`** — endpoint inventory the frontend will consume. (No payload schemas — that's the implementation's job.)
5. **`05-improvements-over-original.md`** — catalog of where we deliberately diverge from the Blazor app, with rationale.
6. **`06-verification.md`** — how to validate the design end-to-end and the open questions that need closing before implementation.

If you're triaging effort for a quick scoping pass, read `00`, the table of contents of `03` (workflow titles + departures lines), and `05`.
