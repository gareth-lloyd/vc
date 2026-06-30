# GAP-048 — Suppliers directory (rename from Contacts) + role taxonomy + type surfacing

- **Severity:** Gap (frontend rename/scoping + data-model role enum) — after
  GAP-045/046.
- **Source:** 2026-06-17 owner Contacts-feature review transcript + the
  2026-06-29 owner Loom follow-up notes; mockup
  `mock_up_analysis/01-new-res-system.md` §2.14 (page already labelled
  **"Suppliers"**); `workflows/05-directory/contact-roles.md`.
- **Files:**
  - `django_res/accounts/enums.py` (`ContactRole`),
    `django_res/properties/models/contacts.py` (`PropertyContactAssignment`)
  - `data_migration/loaders/` (role mapping), FE role dropdowns
  - `frontend/src/features/contacts/` (list scoping + columns + detail),
    `frontend/src/components/layout/Sidebar.tsx` (nav label)

## Problem

(a) **Menu label + scoping (owner ask, 2026-06-29).** The current operator-side
directory is labelled **"Contacts"** and shows *all* `Person` rows. The owner
wants it **renamed "Suppliers"** and **scoped to the operator-side population
only** — owners, villa managers, villa admins, management companies (and
in-resort vendors). Customers and **agents** must **not** appear here: they live
in the **Clients** directory (GAP-047), where agents fold in behind a
direct/agent filter rather than getting their own page (owner overruled Ben's
separate-Agents-page mockup §2.13 — see `10-decisions.md`). The three directory
views over the one `Person` identity are therefore:
- **Clients** (GAP-047) — `kind=CUSTOMER` + agent-capacity people.
- **Suppliers** (this ticket) — operator-side `kind=CONTACT` people with a
  property role (owner/manager/admin/mgmt-co).
- **Companies** (GAP-046) — B2B agency `Organisation`s.

(b) The `PropertyContactAssignment` role taxonomy **diverges** from the
owner's / legacy / mockup §2.14 set (Owner / Agent / Villa Admin / Villa
Manager / Management Company). The built enum is
`OWNER / MANAGER / AGENT / HOUSEKEEPER / OWNERS_REPRESENTATIVE`
(`accounts/enums.py:40-46`) — it **adds** housekeeper / owners_rep and is
**missing** `villa_admin` and `management_company`. Note `01-accounts.md:140`
itself calls the enum the "direct replacement" for the legacy 5, yet it doesn't
match them.

(c) The role/category is **not surfaced** in the Suppliers list (columns are
Name | Company | email | phone | status — no role column) or prominently in the
detail; nor is the broader **contact type** (this person is an owner *and* a
customer) — see the type-badge requirement, owned by **GAP-052**.

## Proposed fix

- **Rename "Contacts" → "Suppliers"** in the nav/title and **scope the list** to
  the operator-side population (capacity filter; reuse the GAP-045 capacity
  `EXISTS` pattern — query-pinned). Customers/agents excluded here.
  - **Naming collision to flag:** "Suppliers" also names the concierge in-resort
    vendor concept (Settings → Concierge Settings → Suppliers, and Q-007). Two
    surfaces share the word — resolve the label (e.g. "Villa Suppliers" vs
    "Concierge Suppliers") so they don't read as the same list. Cross-ref
    [Q-007](q-007-concierge-supplier-directory.md).
- **Reconcile the role enum.** Re-introduce `villa_admin` /
  `management_company`; decide whether to keep `housekeeper` / `owners_rep`
  (plausible additions the owner didn't ask to remove) — **surface the mismatch,
  don't assume deletion.** Touches `accounts/enums.py`,
  `properties/models/contacts.py`, loaders, FE dropdowns. Record the keep/drop
  call in `10-decisions.md`.
- **Allow `Organisation` assignees** — a `management_company` role should be
  able to reference an `Organisation` (GAP-046), not only a `Person`.
- **Surface the role** in the Suppliers list (chip/column) and detail.
- **Address is now on `Person`.** (Corrected 2026-06-29: `town/post_code/country`
  + `address_line_1/2` all landed on `Person` via GAP-045 and are serialized by
  GAP-042. The earlier "deferred to GAP-045 phase-2, not on Person yet" note is
  spent.) Rendering address read-only is done; **making it editable is GAP-052.**

**Caveat 1 (from the UI assessment):** keep the **Suppliers form distinct from
the Clients form** over the shared `Person` identity — roles / linked properties
/ groups here, vs tags / relationships / history on the Clients side (mockup
§2.14 vs §2.12). Tags are **client-only** and must not appear on the Suppliers
detail (see GAP-053).

## Acceptance

- The operator-side directory is labelled **Suppliers**, scoped to
  owner/manager/admin/mgmt-co people (customers + agents excluded); the list
  endpoint is query-pinned. The Suppliers/concierge-Suppliers naming collision
  is resolved (or explicitly recorded).
- Role enum covers the owner's taxonomy (Owner / Agent / Villa Admin / Villa
  Manager / Management Company); the keep/drop call on housekeeper/owners_rep is
  recorded in `10-decisions.md`.
- `management_company` assignments can point at an `Organisation`.
- Suppliers list/detail shows the property role; the cross-directory **type
  badges** (owner/customer/agent) land with **GAP-052**.

## Dependencies

Depends on **GAP-045** (Person), **GAP-046** (Organisation assignees + Companies
directory), **GAP-047** (Clients directory the agents/customers move to).
Type-badge surfacing → **GAP-052**; tag client-scoping → **GAP-053**. Relates to
`workflows/05-directory/contact-roles.md` (its open role/group table-split
question) and [Q-007](q-007-concierge-supplier-directory.md) (the "Supplier"
name collision).
