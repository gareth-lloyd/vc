> **✅ RESOLVED (2026-07-01)** — Shipped on local `main` (unpushed) as Landing 1
> of the contacts-directory cluster. **Widened `/clients`** to agent-capacity
> persons (agency members / deal-agents), added `?repeat=` + `?tags=` overlap
> filters and `is_repeat_customer`/`tags` on the row (`c0efa66`, `Subquery`
> booking_count so the always-on list COUNT stays accurate). **VIP/Trade/Repeat
> one-click chip filters** on the Clients list, composing with capacity / status
> / search (`4faa233`). **Inline (no-dialog) client-scoped tag editor** — a
> Popover checkbox group with an optimistic audited per-edit mutation, gated on
> clients-membership (customer OR agent-capacity), replacing `TagsFormDialog`
> (`5c1888e`). Deferred: none material.

# GAP-053 — Clients directory: VIP/Trade/Repeat chip filters + inline (no-dialog) tag editor

- **Severity:** Gap (frontend-led) — follow-up to GAP-047 (Clients list) and
  GAP-040 (tags).
- **Source:** 2026-06-29 owner Loom follow-up notes:
  - "Filters at the head of the client page table: **trade, vip, repeat. One
    click to select and filter, like selectable chips.**";
  - "Edit contact tag interface should **not require a dialog box. A simple
    solution would be checkboxes.** The list of tags … are only relevant for
    **clients**."
  Plus the 2026-06-17 owner Loom and mockup §2.12 ("type chips VIP | Repeat |
  Trade as filters").
- **Status:** Open.
- **Files:**
  - `frontend/src/features/clients/` — list filter row (chips) + the
    `CustomerProfilePanel` tag editor (currently the GAP-040 checkbox **dialog**).
  - `django_res/accounts/` — Clients list `?tags=` filter already exists
    (GAP-040 overlap filter); the **Repeat** filter needs the derived
    `is_repeat_customer` annotation (GAP-042) exposed as a filter.

## Problem

Two unshipped owner asks on the Clients surface:

1. **Tag chip filters.** GAP-047 proposed VIP/Repeat/Trade filters but **shipped
   only** the direct/agent filter + region chip columns. The owner wants the
   three flags as **one-click selectable chips** at the head of the Clients
   table. The backend `?tags=vip,trade` overlap filter exists (GAP-040), but
   **"Repeat" is a derived badge, not a stored tag** (GAP-040 excluded it;
   GAP-042 derives `is_repeat_customer` = ≥1 booking) — so the Repeat chip must
   filter on the derived annotation, not on `?tags=`.

2. **Inline tag editor, no dialog.** GAP-040 shipped a **checkbox *dialog***
   editor. The owner wants the checkboxes **inline** (no modal). Also: the tag
   set is **client-only** — it must not appear on the Suppliers detail (GAP-048).

## Proposed fix

- **Chip filter row** on the Clients list: VIP / Trade as `?tags=` overlap
  filters, **Repeat** wired to the `is_repeat_customer` derived filter
  (add the filter param + query-pin). Chips are toggle-to-filter (mockup §2.12);
  compose with the existing direct/agent + search filters. Keep "buttons
  disable, never disappear" if any chip is gated.
- **Inline tag checkboxes.** Replace the GAP-040 dialog with an inline checkbox
  group on the `CustomerProfilePanel` (still writes the same `Person.tags`
  `ArrayField`, still audited + erasure-scrubbed). Scope the editor to
  client-kind contacts; hide tags entirely on the Suppliers detail.
- **Verify agents appear in Clients.** The owner folds agents into the Clients
  list (not a separate page). Confirm the GAP-047 `/clients` capacity filter
  includes **agent-capacity** people (has `agency` / used as `.agent`), not only
  `kind=CUSTOMER`; widen it if pure-agent persons are currently excluded.

## Acceptance

- VIP / Trade / Repeat chips filter the Clients list with one click and compose
  with direct/agent + search; the list query stays pinned.
- Tag editing is inline (no dialog), client-scoped, audited; tags do not render
  on the Suppliers detail.
- Agent-capacity people are reachable in the Clients directory.
- Quality gate green (vitest + pytest for the Repeat/agent filter change).

## Dependencies

- Follows **GAP-047** (Clients list + direct/agent filter), **GAP-040** (tags +
  `?tags=` filter), **GAP-042** (`is_repeat_customer` derivation), **GAP-048**
  (tags excluded from Suppliers). Curated/ops-editable taxonomy stays in
  [Q-021](q-021-defaults-and-feature-taxonomy.md).
