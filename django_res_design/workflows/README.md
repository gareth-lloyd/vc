# Villa Collective — Workflow Specifications

Comprehensive technical workflow specifications extracted from the legacy .NET 7 / Blazor Server reservation system at `../../ResSystem/`. Each workflow is a discrete **"job to be done"** — a coherent operation triggered by a user, an external system, or a scheduler, with defined inputs, side effects, and third-party transmissions.

These specifications are the source of truth for the **what** that the Django redesign in this directory must reproduce (or deliberately depart from). They complement the data-model design in `../README.md` and the higher-level product design in `../product-design/`.

> **Legacy provenance caveat.** These specs were extracted from `ResSystem@main`, which is missing the real quote/enquiry Blazor pages (deleted April 2025 while still running in production). The corrected 4-screen quote/enquiry flow — and a trust map for which specs are grounded vs inferred — is in [`legacy-quote-enquiry-reference.md`](./legacy-quote-enquiry-reference.md).

## Reading order

1. [`00-taxonomy.md`](./00-taxonomy.md) — naming convention, file structure, what counts as a "workflow"
2. Each numbered domain folder contains a `README.md` listing its workflows and grouping rationale
3. Individual workflow files use the per-workflow template defined in `00-taxonomy.md`

## Domains

| # | Domain | What it covers |
|---|---|---|
| 01 | [`identity`](./01-identity/) | Authentication, 2FA, password lifecycle, user/admin management, Blazor circuit auth state |
| 02 | [`administration`](./02-administration/) | System-wide lookup data: countries, regions, currencies, collections, groups, tags/features, system config |
| 03 | [`catalog`](./03-catalog/) | Property (villa) master data: overview, rooms, images, features, nearby, finance config |
| 04 | [`pricing`](./04-pricing/) | Seasons, season rates, occupancy-based pricing, the pricing engine that powers quotations |
| 05 | [`directory`](./05-directory/) | Contact records (owners, managers, agents, guests) and their attachment to properties |
| 06 | [`availability`](./06-availability/) | Per-night availability calendar, booking holds, manual blocks, changeover rules |
| 07 | [`enquiry`](./07-enquiry/) | Inbound enquiries (website + staff manual entry), enquiry management lifecycle |
| 08 | [`quotation`](./08-quotation/) | Building, persisting, sending, and converting quotations |
| 09 | [`booking`](./09-booking/) | Confirmed booking lifecycle, owner approval, concierge add-ons, payment schedule generation |
| 10 | [`payment`](./10-payment/) | Payment collection (tokenized + manual), checkout flow, webhook ingestion, pre-auth (disabled) |
| 11 | [`integrations`](./11-integrations/) | Outbound integrations: Zoho CRM, public WordPress site (Res API), Flywire gateway, SMTP email |
| 12 | [`automation`](./12-automation/) | Scheduled background jobs (payment reminders, hold expiry) |

## Cross-domain notes

- **Soft-deletion** is universal: rows are marked with `DeletedAt`/`DeletedBy` rather than removed. Workflows that "delete" usually soft-delete.
- **Stored procedures everywhere**: the legacy system implements ~97 stored procedures (`sp_*` / `SP_*`) that hold business logic. Workflow files cite the SP names verbatim — these are the contracts the Django services replace.
- **Sync flags drive integration outbound**: most mutation workflows set `SyncId = 0` and call `UpdateSyncId(module, id, 0, user, action)`; a separate sync step picks these up and pushes to WordPress.
- **Three integration boundaries**: Zoho CRM (custom modules `VILLA_ENQUIRY`, `VILLA_QUOTATIONS`, `VILLA_BOOKING`, `VILLLA_MASTER` [sic]), the public WordPress site (`WP_Sync_*` endpoints), and Flywire payment gateway. See [`11-integrations/`](./11-integrations/).
- **Known stubs**: several pieces are referenced in code but not committed — `AvailabilityCard`, `ConnectionTracker`, `ClientInfomation`, `AgentInfomation`. Workflow files mark these explicitly.
- **Known disabled features**: tokenized recurring charge to Flywire (`InvokeChargeApi`) and security-deposit pre-auth (`PreAuthPayReqDTO` flow) are commented out in source. They are documented because the Django redesign should decide whether to revive them.

## Relationship to the rest of `django_res_design/`

- The **data-model design** (`../README.md` and `../01-…-09-…md` files) defines the static shape.
- These **workflow specs** define the dynamic behaviour that operates on that shape.
- The **product design** (`../product-design/03-workflows.md`) describes user-facing flows at a higher abstraction. These files go deeper: every field, every stored procedure, every payload.

Discrepancies between this workflow set and either of the other two packages should be resolved by treating these workflow specs as the **as-built** description of the legacy system, and the data-model + product-design as the **target** description of the Django redesign. The redesign may deliberately depart from any workflow here; departures should be called out in `../09-departures.md` or `../product-design/05-improvements-over-original.md`.
