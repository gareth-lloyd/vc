# Legacy tier — Villa Collective as-built (`ResSystem/`)

> **Frozen legacy reference.** This tier documents the behaviour of the legacy
> .NET 7 / Blazor Server reservation system in `../../ResSystem/` — the *what*
> the Django rebuild must reproduce or deliberately depart from. It describes
> the **old** system as-built; it is **not** a description of what we are
> building. The new design lives in [`../design/`](../design/) and the live
> work queue in [`../todo/`](../todo/).
>
> **Redesign callouts inside these files are historical.** Many workflow files
> carry labelled "Open design questions for the Django redesign" / "Django
> redesign requirement" notes captured while the design was being formed. Most
> have since been decided or built — they are retained for provenance, not as
> live proposals. The canonical homes for forward design are
> [`../design/decisions.md`](../design/decisions.md),
> [`../design/departures.md`](../design/departures.md), and the tickets in
> [`../todo/INDEX.md`](../todo/INDEX.md). Live-but-untracked questions harvested
> from these files are collected in
> [`../todo/inv-006-legacy-open-questions.md`](../todo/inv-006-legacy-open-questions.md).

Each workflow is a discrete **"job to be done"** — a coherent operation
triggered by a user, an external system, or a scheduler, with defined inputs,
side effects, and third-party transmissions.

> **Legacy provenance caveat.** These specs were extracted from
> `ResSystem@main`, which is missing the real quote/enquiry Blazor pages
> (deleted April 2025 while still running in production). The corrected 4-screen
> quote/enquiry flow — and a trust map for which specs are grounded vs inferred
> — is in [`quote-enquiry-reference.md`](./quote-enquiry-reference.md).

## Reading order

1. [`00-taxonomy.md`](./00-taxonomy.md) — naming convention, file structure, what counts as a "workflow"
2. Each numbered domain folder under [`workflows/`](./workflows/) contains a `README.md` listing its workflows and grouping rationale
3. Individual workflow files use the per-workflow template defined in `00-taxonomy.md`

## Domains

| # | Domain | What it covers |
|---|---|---|
| 01 | [`identity`](./workflows/01-identity/) | Authentication, 2FA, password lifecycle, user/admin management, Blazor circuit auth state |
| 02 | [`administration`](./workflows/02-administration/) | System-wide lookup data: countries, regions, currencies, collections, groups, tags/features, system config |
| 03 | [`catalog`](./workflows/03-catalog/) | Property (villa) master data: overview, rooms, images, features, nearby, finance config |
| 04 | [`pricing`](./workflows/04-pricing/) | Seasons, season rates, occupancy-based pricing, the pricing engine that powers quotations |
| 05 | [`directory`](./workflows/05-directory/) | Contact records (owners, managers, agents, guests) and their attachment to properties |
| 06 | [`availability`](./workflows/06-availability/) | Per-night availability calendar, booking holds, manual blocks, changeover rules |
| 07 | [`enquiry`](./workflows/07-enquiry/) | Inbound enquiries (website + staff manual entry), enquiry management lifecycle |
| 08 | [`quotation`](./workflows/08-quotation/) | Building, persisting, sending, and converting quotations |
| 09 | [`booking`](./workflows/09-booking/) | Confirmed booking lifecycle, owner approval, concierge add-ons, payment schedule generation |
| 10 | [`payment`](./workflows/10-payment/) | Payment collection (tokenized + manual), checkout flow, webhook ingestion, pre-auth (disabled) |
| 11 | [`integrations`](./workflows/11-integrations/) | Outbound integrations: Zoho CRM, public WordPress site (Res API), Flywire gateway, SMTP email |
| 12 | [`automation`](./workflows/12-automation/) | Scheduled background jobs (payment reminders, hold expiry) |

## Cross-domain notes (legacy as-built)

- **Soft-deletion** is universal in the legacy system: rows are marked with
  `DeletedAt`/`DeletedBy` rather than removed. Workflows that "delete" usually
  soft-delete. (The Django rebuild drops this — see
  [`../design/departures.md`](../design/departures.md).)
- **Stored procedures everywhere**: the legacy system implements ~97 stored
  procedures (`sp_*` / `SP_*`) that hold business logic. Workflow files cite the
  SP names verbatim — these are the contracts the Django services replace.
- **Sync flags drive integration outbound**: most mutation workflows set
  `SyncId = 0` and call `UpdateSyncId(module, id, 0, user, action)`; a separate
  sync step picks these up and pushes to WordPress.
- **Three integration boundaries**: Zoho CRM (custom modules `VILLA_ENQUIRY`,
  `VILLA_QUOTATIONS`, `VILLA_BOOKING`, `VILLLA_MASTER` [sic]), the public
  WordPress site (`WP_Sync_*` endpoints), and Flywire payment gateway. See
  [`workflows/11-integrations/`](./workflows/11-integrations/).
- **Known stubs**: two pieces are referenced in code but genuinely never
  committed — `AvailabilityCard`, `ConnectionTracker`. Workflow files mark these
  explicitly. (`ClientInfomation` and `AgentInfomation` were previously listed
  here in error — they are real, committed components on the `pinned-2025-04-03`
  prod lineage, deleted from `main` in April 2025; see
  [`quote-enquiry-reference.md`](./quote-enquiry-reference.md) §3.1.)
- **Known disabled features**: tokenized recurring charge to Flywire
  (`InvokeChargeApi`) and security-deposit pre-auth (`PreAuthPayReqDTO` flow)
  are commented out in the legacy source. They are documented for completeness;
  whether the rebuild revives them is tracked in `../todo/`.
