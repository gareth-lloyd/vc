# 02 — Frontend Design (React SPA)

A ground-up redesign of the Villa Collective ops tool as a React SPA backed by the Django REST API. This document is the screen-by-screen spec an engineer should be able to build from. Wireframes are described as ASCII; nothing here assumes a specific Figma file.

---

## 1. App Shell & Navigation

### 1.1 Shell Layout

```
+--------------------------------------------------------------+
| Topbar (56px)                                                |
| [Logo] [Site switcher] ... [⌘K Search] [Bell] [+New] [Avatar]|
+--------+-----------------------------------------------------+
|        |                                                     |
| Side   |                                                     |
| nav    |              Content area                           |
| 240px  |   (page header + body + optional right rail)        |
| (col-  |                                                     |
| laps-  |                                                     |
| ible   |                                                     |
| to     |                                                     |
| 64px)  |                                                     |
+--------+-----------------------------------------------------+
```

Three persistent surfaces:

- **Topbar** — global search, brand/site switcher, environment indicator (thin coloured stripe under topbar: green = prod, amber = staging, red = local), quick-create menu (`+ New booking / quote / enquiry / property`), notifications, user menu.
- **Sidebar** — primary navigation grouped. Collapsible to icon-rail. Remembers state in `localStorage`.
- **Content area** — page header (breadcrumbs + title + page-level actions), body, optional right rail (340px, sticks at top) used as a summary/inspector. The right rail is *not* the same thing as the action drawer (which slides over from the right at 480–640px wide and is modal-ish).

### 1.2 Sidebar Groups

The original mixes admin-only nav with daily-use nav. We split it cleanly: Operations (daily), Library (reference), Insights, Admin (settings). Quotes and Enquiries are split because they have different daily workflows.

```
─ OPERATIONS ────────────
  ▢ Dashboard
  ▢ Enquiries          (badge: open count)
  ▢ Quotes
  ▢ Bookings           (badge: needing action)
  ▢ Availability
  ▢ Payments
  ▢ Concierge

─ LIBRARY ───────────────
  ▢ Properties
  ▢ Contacts
  ▢ Collections        (property groups + collections)

─ INSIGHTS ──────────────
  ▢ Reports

─ ADMIN ─────────────────  (collapsed by default; hidden for non-admin)
  ▢ Sites
  ▢ Countries & Currencies
  ▢ Tags
  ▢ Users & Roles
  ▢ System config
```

### 1.3 Layout Primitives

Build these once, use everywhere:

- `<AppShell>` — topbar + sidebar + outlet.
- `<PageHeader>` — breadcrumbs, title, subtitle, status pill, right-aligned action cluster.
- `<TwoColumn>` — main + right rail. Right rail can be sticky or scrollable.
- `<Drawer>` — right-edge modal-ish panel; routable (`?drawer=...`).
- `<TabBar>` — uses URL segments, not local state, so tabs are bookmarkable.
- `<Toolbar>` — filters + search + bulk actions row above tables.
- `<EmptyState>` — illustration slot, title, body, primary CTA.
- `<StatusBadge>` — colour + icon + label (colour alone is the original pain point; we add an icon and the word).

---

## 2. Routing Scheme

React Router v6+ with data routes. URLs are the source of truth for which tab is open, which drawer is open, which filters are applied.

```
/                                   → redirect to /dashboard
/dashboard
/enquiries                          (list)
/enquiries/:id                      (detail page; not a drawer — too much content)
/quotes
/quotes/new                         (cart builder)
/quotes/:id                         (detail / send)
/bookings
/bookings/new                       (wizard)
/bookings/:id                       (detail with tabs)
/bookings/:id/overview              (default tab)
/bookings/:id/finance
/bookings/:id/payments
/bookings/:id/concierge
/bookings/:id/comms
/bookings/:id/owner
/bookings/:id/timeline
/availability                       (multi-villa timeline; default)
/availability/property/:id          (single villa calendar)
/payments                           (cross-booking view)
/concierge                          (cross-booking list)
/properties                         (list)
/properties/:id                     → redirect /properties/:id/details
/properties/:id/details
/properties/:id/pricing
/properties/:id/availability
/properties/:id/people
/properties/:id/media
/properties/:id/settings
/contacts
/contacts/:id
/collections
/reports
/reports/occupancy
/reports/revenue
/reports/owner-statements
/admin/sites
/admin/countries
/admin/currencies
/admin/tags
/admin/users
/admin/config
/owner/...                          (separate owner portal shell; see §7.3)
/booking?ref=<reference>            (guest checkout; reference-scoped, no login; see §7.5)
```

**Drawer-as-route** pattern. When you want a focused edit without losing context:

```
/bookings/:id/payments?drawer=payment&paymentId=42
/properties/:id/people?drawer=contact&contactId=18
/properties?drawer=new
```

The drawer reads its params, opens itself. Closing pops the search params. This gives shareable URLs to a half-open state, useful for support handoffs.

**Nesting rule of thumb:**
- Nest when the parent supplies persistent context (booking header + tabs).
- Stay flat when the screens have nothing structural in common (admin pages).

---

## 3. Primary Screens

### 3.1 Operator Dashboard

Replaces the property-list dashboard. The job: *what do I need to act on today?*

```
+----------------------------------------------------------------+
| Today  •  Tue 12 May 2026                       Site: VC ▾     |
+----------------------------------------------------------------+
| [KPI: Check-ins 4] [KPI: Check-outs 2] [KPI: Open enquiries 9] |
| [KPI: Overdue payments £18,420] [KPI: Quotes awaiting reply 3] |
+----------------------------------------------------------------+
| Arrivals today (4)                          [View all →]       |
|  • Villa Azul       Guest: Mooney         15:00  prepared ✓    |
|  • Casa Norte       Guest: Tan            16:00  not prepared !|
|  • ...                                                         |
+----------------------------------------------------------------+
| Departures today (2)        | Overdue balances (5)             |
|  • ...                      |  • #VC2391 £4,200  +3d          |
|                             |  • ...                           |
+----------------------------------------------------------------+
| Recent enquiries                        Quotes activity         |
|  • Smith — 2 villas, Aug   |  • Quote #QVC184 viewed 2h ago     |
|  • ...                     |  • ...                            |
+----------------------------------------------------------------+
```

- **KPI cards** are clickable filters into deeper pages (clicking "Overdue payments" → `/payments?status=overdue`).
- **Arrivals/Departures** show a prepared/not-prepared flag derived from concierge tasks status.
- Empty state: "Nothing arriving today. Enjoy the quiet."
- Loading: skeleton KPIs + skeleton list rows.
- Error per card (not per page) — one failed widget doesn't blank the dashboard.
- Permissions: owner-portal users see only their own properties' arrivals/departures and never see overdue-balance amounts.

### 3.2 Properties List

```
+----------------------------------------------------------------+
| Properties                                    [+ New property] |
+----------------------------------------------------------------+
| [Search] [Country ▾] [Site ▾] [Tag ▾] [Status ▾] [Bulk ▾]      |
+----------------------------------------------------------------+
| □ | Name        Country  Bedrooms  Rate band   Status   Owner  |
| □ | Casa Norte  Spain    6         €€€         Active   Lopez  |
| □ | ...                                                        |
+----------------------------------------------------------------+
| 1–25 of 84                                  ‹ 1 2 3 4 ›        |
+----------------------------------------------------------------+
```

- Server-driven pagination/sort/filter via TanStack Table + TanStack Query.
- Row click → `/properties/:id`. Avatar/thumbnail in name cell.
- Bulk actions: tag, archive, change site, export.
- Saved filter views ("My active Spanish villas") stored per user.

### 3.3 Property Detail — Tab Grouping

14 tabs collapsed to 6. Right rail shows summary (cover image, key facts, quick actions: "Open in availability", "Create booking", "Create quote").

```
+----------------------------------------------------------------+
| ← Properties  /  Casa Norte                                    |
| [Details] [Pricing] [Availability] [People] [Media] [Settings] |
+--------------------------------------------+-------------------+
|                                            | [Thumbnail]       |
|   Tab body                                 | Casa Norte        |
|                                            | Marbella, Spain   |
|                                            | 6 BR · 12 guests  |
|                                            | Status: Active    |
|                                            | ──────────────    |
|                                            | [Quick actions]   |
+--------------------------------------------+-------------------+
```

Tab contents (mapped from the original 14):

1. **Details** — Overview + Descriptions + House rules + Features + Nearby + Rooms (as a sub-section with its own list and importer button). Long content; uses an internal anchor sidebar inside the tab body.
2. **Pricing** — Rates + Finance settings (commission, tax) + Extras (add-ons that have prices) + Discount rules.
3. **Availability** — Embedded single-villa calendar + manual block management + iCal sync settings.
4. **People** — Contacts mapped to this property (owners, agents, concierge), with the new role-preset permission UI (§3.13).
5. **Media** — Images (drag-reorder grid), floor plans, videos, brochure PDFs.
6. **Settings** — Property-level settings, site visibility, status (Active/Draft/Archived), integration toggles, danger zone.

The two "Import" tabs become buttons inside the relevant tab (`Import rooms` lives in Details → Rooms; `Importers` lives in Settings).

### 3.4 Property Rates Editor

This is the densest screen. The model is: a property has many **Seasons** (date ranges with names like "High 2026") and each season has one or more **Rate Cards** (the actual prices, with weekly/nightly/min-stay/commission/tax/occupancy bands and discount rules).

```
+----------------------------------------------------------------+
| Pricing > Rates                       [+ Season]  [Copy year ▾]|
+----------------------------------------------------------------+
| Seasons (left rail, 280px) | Rate card editor (right)          |
|----------------------------+-----------------------------------|
|  ▸ High 2026               | Season: High 2026                 |
|    1 Jul – 31 Aug          | Dates: [1 Jul 2026]–[31 Aug 2026] |
|    £8,400 / week           | Min stay: [7] nights              |
|                            |                                   |
|  ▸ Mid 2026                | Rate Cards (1)        [+ Add card]|
|    1 May – 30 Jun          |  ┌─────────────────────────────┐  |
|                            |  │ Standard (6 guests)         │  |
|  ▸ Low 2026                |  │ Weekly: £8,400              │  |
|                            |  │ Nightly: £1,300             │  |
|  ▸ Christmas 2026          |  │ Commission: 20%             │  |
|                            |  │ Tax: 10% IVA                │  |
|                            |  │ Occupancy bands:            │  |
|                            |  │  up to 6 — included         │  |
|                            |  │  7–8 — +£200/night          │  |
|                            |  │  9–10 — +£350/night         │  |
|                            |  │ Discounts:                  │  |
|                            |  │  • 14+ nights: −5%          │  |
|                            |  │  • Early bird 90d: −7%      │  |
|                            |  └─────────────────────────────┘  |
|                            | [Preview] shows a calendar strip  |
|                            | with computed nightly rates.      |
+----------------------------+-----------------------------------+
```

Key behaviours:

- **Season list** shows date range and headline weekly rate; warns (amber dot) if a season overlaps another season or leaves an uncovered gap in the year.
- **Year copy** ("Copy 2025 → 2026") shifts all seasons by ~52 weeks anchored on day-of-week, not just calendar date.
- **Inline date conflict resolution** — picking a date that overlaps another season shows a popover with three choices: shrink the other season, replace it, or cancel.
- **Preview strip** under the editor: 12-month tape showing the computed nightly rate (colour heatmap). Read-only, but clicking a date jumps to that season.
- Discounts are a sortable list (priority matters — first match wins, configurable).
- Empty state: "No seasons configured yet. Start with a year template?" with `Copy from another property` and `Use VC default annual template` buttons.
- Permissions: owners see-only; operators edit; admins also edit commission/tax (operators can be locked out of those fields via a feature flag).

### 3.5 Availability — Multi-Villa Timeline (the improved view)

The headline new screen. Replaces the single-villa-only calendar with a Gantt-style tape: one row per villa, horizontal time axis. Date granularity is days; resolution toggles between **Day** (default), **Week**, **Month**.

```
+----------------------------------------------------------------+
| Availability                       [Day][Week][Month]  May 2026|
| Filters: [Country ▾][Tags ▾][Bedrooms ▾][Site ▾][Status ▾]     |
| [Today]  [◂]  May 2026  [▸]                       [+ Block]   |
+----------------------------------------------------------------+
|              | 12| 13| 14| 15| 16| 17| 18| 19| 20| 21| 22| 23  |
| Casa Norte   |░░░|███|███|███|███|███|███|   |   |   |   |▒▒▒  |
| Villa Azul   |   |   |   |▓▓▓|▓▓▓|▓▓▓|▓▓▓|▓▓▓|▓▓▓|███|███|███  |
| Casa Sur     |▒▒▒|▒▒▒|   |   |   |   |   |   |█▌ |███|███|███  |
| ...                                                            |
+----------------------------------------------------------------+
| Legend: █ Booked  ▓ Hold  ▒ VC-Booked  ░ Unavailable  ▌ half  |
+----------------------------------------------------------------+
```

- Sticky left column with villa name and tiny thumbnail. Sticky top date axis.
- Cells are bands that span their actual duration; status colours match the original (available is shown as blank for density). Half-day morning/afternoon variants render as left/right half-fills.
- Click a band → drawer with booking summary + actions (open, edit, cancel).
- Click an empty range (drag to select multiple days) → "Create booking" / "Add block" popover.
- Drag-resize a band edge to change check-in/check-out (optimistic; rollback toast on server reject).
- Drag a whole band vertically to move to another villa (operator confirms; useful for rebookings).
- Keyboard: arrow keys move focused range; `[` and `]` shift visible window.
- Performance: virtualize rows (only render visible villas) and columns when in Day view across >120 days.
- Filters and date window persist in URL.
- Loading: shimmer rows; data fetches per visible date window (request cancellation when scrolling fast).
- Owners only see their own villas; operators see all.

### 3.6 Availability — Single Villa Calendar (familiar)

Linked from a band click, from `/properties/:id/availability`, and from the timeline left-column villa name. Same month grid as the original (familiar), with the same status colours and morning/afternoon halves. Right rail shows the selected day's booking/block details and a "Create block / booking" action.

```
+----------------------------------+------------------+
| Casa Norte — May 2026  [‹][›]    | Selected: 18 May |
|                                  | Booked           |
|  Mo Tu We Th Fr Sa Su            | Guest: Tan       |
|   1  2  3  4  5  6  7            | VC2391          |
|   8  9 10 11 12 13 14            | [Open booking]   |
|  15 16 17 ▓▓ ▓▓ ▓▓ ▓▓            |                  |
|  ...                             |                  |
+----------------------------------+------------------+
```

### 3.7 Bookings List

Fixes the "status is colour-only" pain via a richer status component and a lifecycle column.

```
+----------------------------------------------------------------+
| Bookings                                  [+ New booking]      |
| [Search ref/guest/villa]  [Status ▾] [Stage ▾] [Site ▾] [Date]|
+----------------------------------------------------------------+
| □ | Ref     Villa     Guest   Dates           Stage     £     |
| □ | VC2391 Casa N.   Tan     14–21 May 26    [●●●○○] D! 12,400|
| □ | VC2392 Villa A.  Mooney  10–17 Jul 26    [●●●●○] B  18,200|
| □ | ...                                                        |
+----------------------------------------------------------------+
```

- **Stage** column is a 5-pip progress indicator: Enquiry → Quote → Confirmed → Deposit paid → Balance paid → Departed. Tooltip names each pip; a `!` overlay flags overdue.
- Letter suffix is the financial state at a glance (`D!` = deposit overdue, `B` = balance paid). Operators learn it fast; tooltip explains.
- Row click → full page (booking is too dense for a drawer).
- Bulk actions: send reminder, export, mark cancelled (admin only).
- Saved views per user ("Confirmed this month", "Overdue deposit", "VC-side bookings").

### 3.8 Booking Detail — Tabbed with Right Rail

The 11-card scroll becomes 6 tabs + a persistent right rail summary.

```
+----------------------------------------------------------------+
| ← Bookings / VC2391                                           |
| Casa Norte · Tan party · 14–21 May 2026                        |
| [Overview][Finance][Pay][Concierge][Comms][Owner][Timeline]    |
+--------------------------------------------+-------------------+
|                                            | VC2391           |
|   Tab body                                 | Confirmed         |
|                                            | 14–21 May (7n)    |
|                                            | 8 guests          |
|                                            | ──────────────    |
|                                            | Total   £12,400   |
|                                            | Paid    £4,000    |
|                                            | Due     £8,400    |
|                                            | Next: balance     |
|                                            |   due 1 May 26    |
|                                            | ──────────────    |
|                                            | [Send to guest]   |
|                                            | [Send to owner]   |
|                                            | [Cancel booking]  |
+--------------------------------------------+-------------------+
```

Tabs:

1. **Overview** — Status, customer, payer (if different), agent, internal notes, key dates, booking details (guests, special requests). One column, sectioned.
2. **Finance** — Line items table (rental, extras, discounts, taxes), totals, currency, commission breakdown, security-deposit amount. Edit inline.
3. **Payments** — The three-track timeline (§3.12).
4. **Concierge** — Line items + tasks (§3.14).
5. **Comms** — Per-booking communications history (every email sent against this booking, sourced from `EmailLog` — see `10-comms.md`). Columns: timestamp, recipient, template (key + version), rendered subject, status, opens/clicks (when provider events are wired). Per-row actions: **View payload** (modal with rendered HTML + plaintext alternate) and **Resend** (creates a new `EmailLog`, does not mutate the original). Top-of-tab action: **Compose** — template picker plus free-form override fields → preview → send. Replaces the legacy "no per-booking comms view at all" status quo where outbound mail went to per-day plaintext files only.
6. **Owner** — Owner details, owner-side payout schedule, owner notes (separate from guest-facing notes).
7. **Timeline** — Audit log of every state change, sent email, payment received, edit by user, with filter by event type.

The right rail is **always visible** across all tabs, so the operator always knows what the booking is and what to do next.

### 3.9 Booking Creation Wizard

For new bookings only. Existing bookings always use the tabbed view; the wizard would feel patronising on an edit.

```
+----------------------------------------------------------------+
| New booking                              [Save & exit] [Close] |
| (1) Dates & villa  →  (2) Guest  →  (3) Pricing  →  (4) Review |
+----------------------------------------------------------------+
| Step content...                                                |
|                                                                |
| [← Back]                                            [Next →]   |
+----------------------------------------------------------------+
```

Steps:

1. **Dates & villa** — Pick site, dates, guest count. Live list of matching villas (status, rate, conflicts shown inline). Selecting one locks in the villa.
2. **Guest** — Customer details. If `payer` differs from `guest`, expand to second sub-form. Existing-contact autocomplete avoids duplicates.
3. **Pricing & deposits** — Auto-computed line items from rate cards; operator can override. Three-track deposit setup: deposit %, balance due date, security deposit amount. Currency picker (defaults from property).
4. **Review & confirm** — Read-only summary, plus a checklist (send confirmation email, request deposit, notify owner). Each checklist item is a defaulted-on toggle; clicking `Confirm` runs them.

Wizard state held in a single React Hook Form instance, persisted to `sessionStorage` so a refresh doesn't blow it up. `Save & exit` creates a draft booking; the user can resume later from `/bookings?status=draft`.

### 3.10 Quote Builder

The cart UI the original was missing.

```
+----------------------------------------------------------------+
| New quote                          [Save draft] [Send to guest]|
+----------------------------------------------+-----------------+
| Criteria                                     | Quote cart (2)  |
| Dates: [10–17 Aug 2026]  Guests: [8]         | ┌─────────────┐ |
| Country: [Spain ▾]  Tags: [Pool ▾][Sea ▾]    | │ Casa Norte  │ |
|                                              | │ 7n  £8,400  │ |
| Matching villas (12)                         | │ [Remove]    │ |
| ┌────────┐ ┌────────┐ ┌────────┐             | └─────────────┘ |
| │ Casa N.│ │ Villa A│ │ Casa S.│             | ┌─────────────┐ |
| │ 6 BR   │ │ 5 BR   │ │ 8 BR   │             | │ Villa Azul  │ |
| │ £8,400 │ │ £7,200 │ │ £9,800 │             | │ 7n  £7,200  │ |
| │ [Add+] │ │ [Add+] │ │ [Add+] │             | │ [Remove]    │ |
| └────────┘ └────────┘ └────────┘             |                 |
| ...                                          | Subtotal £15,600|
|                                              | [Preview →]     |
+----------------------------------------------+-----------------+
```

- Cards in the grid show availability for the chosen dates (greyed-out if conflict; hovered shows reason).
- Drag-add or button-add to cart.
- Cart shows per-villa line; clicking a line opens an inline editor (override price, add note for this villa option).
- `Preview` renders the guest-facing version (PDF + email body) in a modal.
- `Send to guest` requires recipient email, optional cover note; queues a tracked send (open/click events feed into Quotes activity on dashboard).
- A quote can have N villa options; the guest picks one which converts to a booking via the wizard pre-filled.

### 3.11 Enquiry Inbox

Kanban + list views, toggle in the header. Kanban is the default because enquiries are pipeline.

```
+----------------------------------------------------------------+
| Enquiries     [Kanban] [List]     [+ New]   Filters: ...       |
+----------------------------------------------------------------+
| New (4)        | Qualifying (3) | Quote sent (5) | Won (2)     |
|----------------+----------------+----------------+-------------|
| ┌────────────┐ | ┌────────────┐ | ┌────────────┐ | ...         |
| │ Smith      │ | │ Tan        │ | │ Mooney     │ |             |
| │ 2 villas   │ | │ 1 villa    │ | │ QVC184 sent │ |             |
| │ Aug 26     │ | │ Jul 26     │ | │ 2d ago     │ |             |
| │ source:    │ | │ source:    │ | │ ...        │ |             |
| │  website   │ | │  agent     │ | │            │ |             |
| └────────────┘ | └────────────┘ | └────────────┘ |             |
+----------------------------------------------------------------+
```

- Drag between columns to change status.
- Card click → enquiry detail (`/enquiries/:id`) — full page because there's correspondence history.
- A "Lost" lane is reachable via overflow column (`▸ Lost (28)`) so it doesn't clutter.
- List view is for power users who want sortable columns.

### 3.12 Payments View (per booking)

Three parallel tracks. Each track is a row of milestones.

```
+----------------------------------------------------------------+
| Payments — VC2391                                             |
+----------------------------------------------------------------+
| Deposit (30%)                                                  |
|  ●─────────●─────────○         £3,720 of £3,720  ✓ Paid        |
|  Invoice    Paid                                                |
|                                                                 |
| Rental balance                                                  |
|  ●─────────○─────────○         £0 of £8,680     Due 1 May 26   |
|  Invoice    Reminder  Paid                                      |
|  [Send reminder]  [Mark received]  [Refund]                    |
|                                                                 |
| Security deposit                                                |
|  ○─────────○─────────○         £0 of £1,000     Hold pre-stay  |
|  Hold       Released                                            |
+----------------------------------------------------------------+
| Transactions                                                    |
|  12 Apr 26  £3,720  Flywire txn_xxx  Deposit  by ops           |
|  ...                                                            |
+----------------------------------------------------------------+
```

- Each track has its own status, due date, and action buttons.
- Transactions table at bottom is the audit log.
- Inline edits (e.g., change due date) via right-rail drawer (`?drawer=payment&track=balance`).
- `/payments` (cross-booking) is the same structure flipped: rows are booking-payments, with filters by status (overdue / due in 7d / paid) and a per-row mini-track visual.

### 3.13 Contact Detail — Simplified Permissions

Original: 12+ boolean flags per contact-property mapping (6 access + 6 notify). We replace with **role presets** + an "Override" toggle that exposes the raw flags only when needed.

```
+----------------------------------------------------------------+
| Lopez Properties SL                                            |
| [Details] [Properties (4)] [Notes] [Audit]                     |
+----------------------------------------------------------------+
| Property mappings                                              |
| ┌────────────────────────────────────────────────────────────┐ |
| │ Casa Norte                            Role: Owner ▾  ⚙     │ |
| │ Notifications: Bookings, Payments     [⚙ Customize]        │ |
| └────────────────────────────────────────────────────────────┘ |
| ┌────────────────────────────────────────────────────────────┐ |
| │ Villa Azul                            Role: Agent ▾  ⚙     │ |
| │ Notifications: Bookings only          [⚙ Customize]        │ |
| └────────────────────────────────────────────────────────────┘ |
+----------------------------------------------------------------+
```

Role presets (configurable in admin):
- **Owner** — full view of own property bookings, finance, owner notes; notified on confirmed bookings + payouts.
- **Agent** — sees bookings they originated; notified on those bookings.
- **Concierge** — sees concierge tasks, guest contact within 7d of stay; notified on concierge requests.
- **Read-only** — view bookings, no finance.

`⚙ Customize` opens a drawer with the raw 12 toggles for the rare exception case. The role then displays as "Owner (custom)" so it's obvious.

### 3.14 Concierge Management

Two surfaces:

- **Per-booking concierge tab** — line items (airport transfer, chef, etc.), each with status (requested / confirmed / cancelled), assignee, price, payment status, internal notes. Inline-add common items from a property's concierge catalogue.
- **Cross-booking `/concierge`** — list of upcoming concierge items across all bookings, filterable by date / villa / supplier, for the concierge desk to action.

```
+----------------------------------------------------------------+
| Concierge — VC2391                          [+ Add service]   |
+----------------------------------------------------------------+
| Service        When         Supplier   Price  Status    Paid   |
| Airport pickup 14 May 15:00 GoTransfer  £180  Confirmed Yes ✓  |
| Chef (5n)      15–19 May    M. Garcia   £900  Requested No  !  |
| ...                                                            |
+----------------------------------------------------------------+
```

### 3.15 Reports

Three reports, each its own page under `/reports`:

- **Occupancy** — heatmap (villas × months), with filters; export CSV.
- **Revenue** — bar chart per month + table; filters by site, country, currency (normalise to a chosen base for the chart, show original currency in tooltips).
- **Owner statements** — picker (owner + period) → generated statement with line items per booking, payout summary, downloadable PDF. Sent-to-owner status tracked.

Each report page has a "saved query" mechanism so an operator can save "Q3 2026 Spain occupancy" and revisit.

### 3.16 Settings Screens

Plain CRUD tables for **Sites**, **Countries**, **Currencies**, **Tags**, **Users**, **System config** (key/value). All admin-only. **Tags** and **Collections** appear under Library too (read for all, edit for admin).

Users screen includes role assignment, 2FA reset, last-login info, deactivate (no hard delete). Audit log per user is reachable from each row.

---

## 4. Reusable Components & Design System

### 4.1 UI Library Recommendation

**shadcn/ui + Tailwind CSS + Radix primitives.**

Why:
- shadcn is *copy-the-component-into-your-repo*, not a runtime dep, so we can mutate components freely (this app needs custom tables, calendars, drawers — opinionated libraries fight us).
- Radix gives accessibility primitives for free (focus-trap, ARIA on dialogs, menus, popovers).
- Tailwind keeps styling colocated and gives us design tokens.
- Easy to layer in TanStack Table, TanStack Query, React Hook Form.

Honourable mentions and why-not:
- **Mantine** is fine but its baked-in styling collides with Tailwind and its DataTable is weaker than TanStack Table for server-driven data.
- **Chakra** is solid but the maintainer change (v3) introduced churn.
- **AntD** is dense, opinionated, enterprise-Java in feel; escaping its look is more work than starting from shadcn.

### 4.2 Component Inventory

Build once, use everywhere:

- `<DataTable>` — wraps TanStack Table, server-driven pagination/sort/filter, column visibility persisted, bulk-select, sticky header.
- `<Toolbar>` — search input + filter chips + bulk-action menu.
- `<FilterPopover>` — typed filter (date range, multi-select, enum) with apply/clear.
- `<Drawer>` — right-edge panel, routable, focus-trapped.
- `<Stepper>` — used in the booking wizard.
- `<Tabs>` — routable; underline style.
- `<StatusBadge>` — icon + colour + label.
- `<MoneyDisplay value currency />` — always renders the ISO code (`£12,400 GBP`) for unambiguity.
- `<DateRange>`, `<DatePicker>` — wraps `react-day-picker` over date-fns.
- `<Calendar>` — single-villa month view.
- `<Timeline>` — multi-villa Gantt; built on a virtualized grid.
- `<RichTextEditor>` — Tiptap with a constrained toolbar (bold, italic, lists, links). No font/colour pickers.
- `<CommandPalette>` — Cmd-K, with routes + entity search.
- `<ConfirmDialog>` and `<UndoToast>` — used per §6.
- `<EmptyState>`, `<ErrorState>`, `<Skeleton>` — present everywhere there's async data.

### 4.3 Rich Text

Recommend **Tiptap** (ProseMirror-based) with a narrow, locked-down toolset. Rationale:

- Original has WYSIWYG everywhere; users expect rich text in notes/descriptions/house rules.
- Markdown would force operator retraining and break copy-paste from Word.
- Tiptap lets us strip features per-context (guest-facing description allows images; internal note doesn't).
- Output stored as HTML, sanitized server-side.

### 4.4 Forms

**React Hook Form + Zod**. Why:

- The booking wizard, property detail, and rates editor have large, partly-conditional forms. RHF's uncontrolled approach keeps re-renders cheap.
- Zod schemas double as TypeScript types (`z.infer`) and run server-shape validation client-side; share the schema with the API contract.
- Field-level validation feels native, error summaries are easy.
- The wizard's "save draft" works by serializing the RHF state.

### 4.5 Dates & Time Zones

- **date-fns** for date math (lighter than moment/luxon, tree-shakeable). For tz-aware ops, `date-fns-tz`.
- Storage: all timestamps as UTC ISO strings server-side; rendering uses the **property's** local time zone for stay dates (a 14 May check-in at Casa Norte is 14 May in Spain, regardless of where the operator is).
- The user's display TZ is used for system events (audit log, "received at 14:23 your time").
- A small `<LocalTimeHint>` component shows "(your time: 13:23)" next to property-local times when the operator's TZ differs.

---

## 5. State, Data Fetching, Async

### 5.1 Server State — TanStack Query

Why TanStack Query:
- Caches per-key, invalidates per-key, deduplicates concurrent requests.
- Built-in stale/refetch/retry/backoff; window-focus refetch is gold for an ops tool where you leave and come back.
- Mutations + `onMutate` give clean optimistic updates for the calendar.
- Devtools panel speeds up debugging.

Query-key conventions:
```
['properties', filters]
['property', id]
['property', id, 'rates']
['bookings', filters]
['booking', id]
['booking', id, 'payments']
['availability', { window, villaIds }]
```

A small helper builds keys consistently to avoid stale-cache bugs.

### 5.2 Client State — Zustand for cross-cutting

- `useUiStore` — sidebar collapsed, theme, last-used site.
- `useAuthStore` — current user, roles, permissions, mfa state.
- `useFiltersStore` — only when we need to share filters across two co-located views (e.g., dashboard "overdue" KPI passing to `/payments`).

Everything else stays in component state. We do **not** mirror server data into Zustand.

### 5.3 Optimistic Updates

Calendar drag-resize and drag-move are the highest-friction interactions. Use TanStack Query's `onMutate` to:

1. Snapshot the current cache for that date window.
2. Apply the new band position immediately.
3. On error, restore the snapshot and show a toast: "Couldn't move booking — Casa Norte is blocked 19–21 May."
4. On success, invalidate to reconcile with server-computed totals (rates may differ for new dates).

### 5.4 Polling vs Websockets

- **Polling (60s)** for the calendar `availability` query, plus refetch on window focus. Cheap, simple, fine for ops where "near real-time" is enough.
- **Websockets** only if/when we add live presence ("Sara is editing this booking") or instant-update gues portal. Not required at launch.

---

## 6. Cross-cutting UX

### 6.1 Drawers vs Modals

Use **right-rail drawers** for edits that benefit from context retention:
- Edit guest details from a booking → drawer (booking still visible behind).
- Edit a payment line → drawer.
- Add a contact to a property → drawer.

Use **modals** only for:
- Confirmation of destructive actions.
- Self-contained flows that intentionally block (preview-send-quote, MFA challenge).

### 6.2 Command Palette (Cmd-K)

A `<CommandPalette>` opens on `Cmd/Ctrl + K`. Sections:

- **Go to** — routes (`Dashboard`, `Availability`, etc.).
- **Find** — fuzzy search across bookings (by ref `VC2391` or guest), properties, contacts, quotes (`QVC184`). Backend endpoint `/search?q=`.
- **Actions** — `New booking`, `New quote`, `Send reminder for #VC2391`.

Keyboard-only: a power user creates a booking in three keystrokes.

### 6.3 Toasts, Confirms, Undo

- **Toasts** for completed actions ("Booking updated"). Bottom-right, 4s.
- **Undo-toasts** for reversible destructive actions ("Booking cancelled — Undo (10s)"). 10s window where the server operation is deferred.
- **Confirm dialogs** for actions where undo is impractical: deleting a property, processing a refund, sending an email to a guest.

The pattern: prefer undo-toast; reach for confirm only when the action has external side effects.

### 6.4 Multi-Currency Display

Hard rule: **never render a bare number for money**. The `<MoneyDisplay>` component always shows the currency code (`£12,400 GBP`, `€8,400 EUR`). Reports normalise to a chosen base for charts, but tooltips and tables always show the originating currency.

### 6.5 Bulk Actions

Wherever there's a list — bookings, properties, payments, enquiries — a multi-select checkbox column enables a bulk-actions menu. The menu is contextual (selecting rows in different statuses disables incompatible actions and explains why via tooltip).

---

## 7. Auth & Permissions in the UI

### 7.1 Auth Screens

- **Login** — email + password; "Remember device" toggle; "Forgot password" link.
- **Forgot password** — email entry → check-email screen.
- **Reset password** — token-based, accessed from email link.
- **2FA** — TOTP code entry on login; admin-forced for users with `is_admin` and any operator who touches refunds.
- **First-run** — invited users land on a "set password + 2FA" flow.
- **Session expired** — silent token refresh; on hard fail, route to `/login?next=...`.

### 7.2 Role-Conditional Menus

The sidebar reads from `useAuthStore.permissions`. Admin-only items disappear (not just disable) for non-admins. Route-level guards in the router redirect non-permitted users to `/dashboard` with a toast.

### 7.3 Owner Portal

Owners get a **separate shell** under `/owner/*`. Same React app, different layout (simpler topbar, no Admin/Library sections). Server enforces that owners only see their own properties and that finance fields are filtered.

```
/owner/dashboard         (my villas at-a-glance)
/owner/properties/:id    (read-only or limited edit)
/owner/bookings          (my villas' bookings)
/owner/statements        (their owner statements)
```

Operators with the "view as owner" permission can preview the owner portal for a given owner (admin tool).

> **Scope note.** The owner portal above is an operator/owner-facing surface. The separate, much larger **post-booking guest portal** (itinerary, messaging, concierge requests, document vault) remains **deferred** — see `11-milestones.md`. Do not conflate it with the narrow guest checkout in §7.5, which is the only guest-facing surface in Milestone 1.

### 7.4 Property-Scoped Access (client-side)

Permissions returned per session include `property_ids: number[]` or `all`. Lists filter client-side after server-side filtering, but the source of truth is always server enforcement (client filtering is UX-only — never security). UI hides fields rather than disables when the user can't see them; disables when they can see but not change.

### 7.5 Guest Checkout (reference-scoped, Milestone 1)

A single guest-facing screen that lives in this same React SPA but **outside** the operator/owner shells. It is hosted at `portal.villacollective.com/booking?ref=<reference>` (off WordPress; see `10-decisions.md`) and is part of **Milestone 1** — see `11-milestones.md` for the authoritative phasing.

This is **not** an authenticated guest account and **not** the full post-booking guest portal (itinerary, messaging, concierge — all **deferred**, see §7.3 scope note and `11-milestones.md`). It is a deliberately narrow checkout: a guest follows a link from a confirmation/payment-request email, the booking is looked up by its `reference` (an unguessable token, not a sequential id), the guest reviews their booking, supplies/confirms personal details, and pays.

No sidebar, no command palette, no site switcher — a clean, single-column, mobile-friendly layout with the Villa Collective brand topbar only.

```
+--------------------------------------------------------------+
| Villa Collective                                            |
+--------------------------------------------------------------+
|  Your booking — Casa Norte                                  |
|  14–21 May 2026 (7 nights) · 8 guests                       |
|  ──────────────────────────────────────────────            |
|  (1) Your details  →  (2) Payment                           |
|                                                              |
|  Lead guest name   [ ........................ ]             |
|  Email             [ ........................ ]             |
|  Phone             [ ........................ ]             |
|  ──────────────────────────────────────────────            |
|  Total            £12,400 GBP                               |
|  Due now (deposit) £3,720 GBP                               |
|                                                              |
|              [ Continue to payment → ]                      |
+--------------------------------------------------------------+
```

- **Access** — reference-scoped only. The `ref` token resolves a single booking server-side; no login, no session, no access to any other booking. An expired/invalid/already-paid reference shows a friendly terminal state ("This payment link is no longer active — contact us") rather than the operator login.
- **Step 1 — Your details** — review booking summary (villa, dates, guests, line-item total via `<MoneyDisplay>`); confirm/complete lead-guest personal info (name, email, phone). Pre-filled from the booking where known.
- **Step 2 — Payment** — hand off to **Flywire** for the amount due (deposit or balance, as the booking dictates). On return, show a confirmation state; payment status reconciles server-side via the Flywire webhook (the screen does not trust the client redirect as proof of payment).
- Reuses existing primitives (`<Stepper>`, `<MoneyDisplay>`, RHF + Zod, `<EmptyState>`/`<ErrorState>`) but renders in its own minimal shell, not `<AppShell>`.
- Fully responsive — guests are frequently on phones. Unlike the operator rates editor (§8.3), this screen *must* work at phone width.

---

## 8. Accessibility & Responsive Notes

### 8.1 Desktop-first

Primary breakpoint: ≥1280px (operator at desk). Lay out for that.

### 8.2 Tablet

≥768px: sidebar collapses to icon-rail by default; right rail becomes a toggleable drawer instead of always-on; data tables become horizontal-scroll containers with sticky first column. The multi-villa timeline is usable at tablet width but only at Week or Month resolution.

### 8.3 Phone

<768px: support a **manager-on-the-road** subset:
- Dashboard (read-only KPIs).
- Bookings list (compact card view).
- Booking detail (tabs stack vertically).
- Availability — single villa only.
- Payments mark-received.

Property rates editor, quote builder, multi-villa timeline are explicitly **not** mobile-supported; show a friendly "Open this on a larger screen" placeholder. Don't pretend.

### 8.4 Keyboard Navigation

- `Cmd/Ctrl + K` — command palette.
- `Cmd/Ctrl + /` — keyboard shortcut help dialog.
- `g d`, `g b`, `g p`, `g a` — go to dashboard / bookings / properties / availability.
- `n b`, `n q`, `n e` — new booking / quote / enquiry.
- Within a list: `j`/`k` move row focus, `Enter` opens, `x` toggles select.
- Within a calendar: arrows move focus, `Enter` opens, `Space` selects a range.
- All interactive elements reachable via Tab; visible focus rings (Tailwind `ring-2 ring-offset-2`).
- All form fields have `<label>`s; errors are announced via `aria-live="polite"`.
- All icons that are interactive have `aria-label`s; status badges include text (not colour-only).

### 8.5 Colour & Contrast

- All status colours meet WCAG AA against their background.
- Calendar status colours keep the original semantic mapping (familiarity) but pair each with an icon for colour-blind users.
- Dark mode is *not* in scope for v1; design tokens are in place to add it later without refactor.

---

## Closing Notes

This design preserves the operator's existing mental model (Properties, Bookings, Availability, Quotes, Enquiries, Concierge, Contacts) while attacking each pain point with a specific change: a dashboard that earns its place, a property detail that fits on one screen, status indicators that say what they mean, a booking page that doesn't require thirty seconds of scrolling, a calendar that finally shows the portfolio, a quote builder that matches the actual workflow, and a permissions model an operator can hold in their head.

The technical stack — Vite + React + TypeScript + React Router + TanStack Query + TanStack Table + React Hook Form + Zod + shadcn/ui + Tailwind + Tiptap + date-fns + Zustand — is conventional on purpose. Every choice has a thriving ecosystem; nothing here is a gamble. The novelty should live in the product, not the substrate.
