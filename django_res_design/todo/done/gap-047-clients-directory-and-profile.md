# GAP-047 — Clients (renter) directory: a browsable list + direct/agent filter

> **✅ RESOLVED (2026-06-23)** — shipped to local `main` (merge `16680fd`), 4
> units (endpoint → region aggregation → FE list/nav → region chip columns):
> - **`/clients` directory list endpoint** over `Person` filtered to customer
>   capacity, with the direct/agent filter — `0bb1066`.
> - **Quoted/booked region aggregation** on `/clients` (query-pinned) — `8778d78`.
> - **Clients directory list page** + `Sidebar` nav entry + route — `780ad2b`
>   (+ Sidebar nav-order test `58a0d2d`).
> - **Quoted/booked region chip columns** on the list — `9f70fd4`.
>
> Scope was the standalone *directory/list* only, as specified. The customer
> **detail/profile** and its building blocks remain open in their own tickets:
> tags → **GAP-040**, linked contacts → **GAP-041**, Customer 360 → **GAP-042**.

- **Severity:** Gap (frontend + endpoint) — after GAP-045 / GAP-046
- **Source:** 2026-06-17 owner Contacts-feature review transcript
  ("it's important for the new system to have a **client list**" … filter
  direct vs agent, plus VIP/repeat/trade); mockup
  `mock_up_analysis/01-new-res-system.md` §2.12.
- **Files:**
  - `django_res/accounts/` — a Clients **list** endpoint over `Person`
    (filtered to customer capacity)
  - `frontend/src/features/clients/` (new directory list),
    `frontend/src/components/layout/Sidebar.tsx` (nav)

## Scope note — this ticket is the *directory/list* only

The customer **profile/detail** and its building blocks are already ticketed
from the same Loom; **do not re-specify them here** — cross-reference:
- **Tags** (VIP/repeat/trade/…) → **GAP-040**.
- **Standing linked contacts** (spouse/child/PA) → **GAP-041**.
- **Customer 360 profile + enquiry/booking history** → **GAP-042**.

This ticket adds only the standalone, browsable **Clients section** the owner
asked for — the list those detail views are reached *from*.

## Problem

There is no nav entry / browsable list of clients (renters). The data exists
(`Person` post-GAP-045; the `GET /guests/{id}/…` history endpoints re-homed on
Person), and the *detail* is covered by GAP-042, but the operator can't open a
"Clients" section, search it, and filter it the way the owner described.

## Proposed fix

- **Clients directory (FE)**: nav entry + list (search, status) with the
  owner's filters — **direct vs agent** (agent = has `Person.agency` / used as
  an `.agent`, per GAP-046) and **VIP/repeat/trade** (the GAP-040 tags surfaced
  as list filters). Row → opens the GAP-042 profile.
- **List endpoint** over `Person` filtered to customer capacity; query-pinned
  (`assert_max_queries`, see GAP-045 caveat 3 on `EXISTS`/capacity filtering).

**Caveat 1 (UI assessment):** the Clients surface is capacity-scoped — distinct
from the Villa-Contacts list (GAP-048), though both sit over one `Person`
identity (mockup §2.12 vs §2.14).

**Caveat 2 (open UI question):** a **dual-capacity human** (owner who also
rents; agent who books personally) is **one** `Person` appearing in **both**
the Clients and Villa-Contacts lists. More correct (one human/history) but cuts
against the owner's "two separate lists" mental model — decide context-scoped
presentation; surface the overlap, don't hide it.

## Acceptance

- A Clients section is reachable from nav; the list searches and filters by
  direct/agent and VIP/repeat/trade; rows open the GAP-042 profile.
- List endpoint over `Person` is query-pinned.
- No duplication of GAP-040/041/042 model or detail work — only the list/nav.

## Dependencies

Depends on **GAP-045** (Person + capacity), **GAP-046** (agent capacity → the
direct/agent filter). Consumes **GAP-040** (tags as filters), **GAP-042**
(profile opened from rows). Mockup §2.12 is the reference UI.
