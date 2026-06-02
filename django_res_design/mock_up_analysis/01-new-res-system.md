# New Reservation System — Mockup Analysis

> Source: https://vc-new-res-system.netlify.app/ (single-bundle React 18 SPA, dev build, no router; navigation is in-process via `window.__vcNav(pageName, params)`).
> Reviewed against: `django_res_design/workflows/` and `django_res_design/product-design/`.

---

## 1. Summary

The mockup is a staff-facing rebuild of the legacy `ResSystem/` UI — a 15-page SPA covering Dashboard, Quotes & Enquiries (with embedded Rate Lookup), Bookings (live + Archive), per-booking Concierge & Experience module, Availability calendar, Properties (with 13-tab detail), Clients (B2C guests), Agents (B2B sales partners, individual + company), Suppliers (in-resort vendors), Finance & Invoicing, Feedback (post-stay), CSV Import with saved mappings, and a multi-section Settings hub. Everything is wired with rich demo data and modal interactions.

**Coverage estimate (rough):**

- ~70 % of the `workflows/` surface is represented (enquiry, quotation, booking, payment, availability, catalog, directory, taxonomy, configuration). Notably absent: `01-identity/authentication.md` (no login screen), `01-identity/password-management.md`, `11-integrations` (Flywire, Zoho push UI), `12-automation/scheduler-jobs.md` admin.
- ~80 % of `product-design/02-frontend-design.md §3 Primary Screens` is realised — the only gaps are the multi-villa **availability timeline** (§3.5), `§3.15 Reports`, the Owner Portal, the **Cmd-K command palette** (§6.2), and the **Booking Creation Wizard** (§3.9 — though "+ New booking" exists).
- ~25 % of the mockup is **net-new** vs the existing spec — see callouts below.

**Top 5 most impactful "this is new":**

1. **Per-booking Concierge & Experience module** with five tabs (Overview, Payment Lists, Timeline, Post-Stay, Suppliers) including per-line supplier costs, client margin, payment-list workflow, day-by-day stay timeline. Goes far beyond `workflows/09-booking/concierge.md` and `product-design/02-frontend-design.md §3.14`.
2. **Post-stay feedback module** — first-class screen with aspect ratings (overall/villa/concierge/comms/transfers/chef/boat/etc.), 4-state workflow (new → acknowledged → responded → closed), prize-draw flag, threaded reply, low-score alerts, prize opt-in. **Nothing in the workflows or product-design specs covers this.**
3. **Regional Managers** — a new role/entity per country×region with `lead` + `backup` users and a phone number, plus a Notes & Comms thread on Booking Detail visibly tagged "Regional manager". Spec only has Contact roles like Villa Manager / Villa Admin (`workflows/05-directory/contact-roles.md`).
4. **Discount-split semantics on Booking** — radio choice between "Commission split (owner shares the discount)" vs "VC absorbs in full" with live Net-to-Owner math. Spec discounting (`workflows/08-quotation/persistence.md §Apply discount`) does not model who absorbs the discount.
5. **CSV Import with saved presets** ("Standard villa-export CSV", "Boukari spreadsheet") — a full mapping-preset UI mapping ~100 grouped target fields. Spec has nothing on bulk property import; `workflows/03-catalog/property-rooms.md §Bulk import rooms from CSV` is the only adjacent piece.

Honourable-mention new ideas: **Quintessential / Signature** concierge level enum on every booking, **Agent type = Individual | Company (with Sub-Agents)** entity model, **Concierge "service status" enum** (`not_started | working_on_it | waiting | arranged_independently | not_required | done`), **payment-list lock + Mark-Paid workflow**, **per-property "Sync to Web" button** and global **Sync to Web** on Properties list.

---

## 2. Screen inventory

Top-level nav (sidebar) — extracted from `_NAV` in the bundle (root JS, search for `const _NAV = [`):

```
Dashboard
Quotes & Enquiries
  └ Rate Lookup            (sub-tab, becomes own page)
Bookings
  └ Archive Bookings       (sub-tab, separate page from main Bookings)
Concierge                  (= Experience & Concierge overview)
Availability
Properties
  └ Overview / Information / Rates / Finance / Availability / Rooms / Features
     / Nearby / Contacts / Settings / Images / Descriptions   (only shown when a property is open)
Clients
Agents
Suppliers
Finance                    (= Finance & Invoicing)
Feedback                   (= post-stay feedback)
Settings
  └ Countries / Regional Managers / Currencies / Config / Users / Features /
     Property Defaults / Collections / Property Groups / Concierge Settings / Import
```

`PAGE_MAP` (App.tsx-equivalent, near end of bundle) wires every label to a `*Page` component. Property sub-tabs are injected dynamically when `PropertyDetailPage` is the current page.

### 2.1 Dashboard

- **Purpose:** operational morning-coffee view across the whole business.
- **UI elements:**
  - 6 KPI cards: `Revenue (Mar)`, `Confirmed Bookings`, `Arrivals This Week`, `Open Quotes`, `Concierge Actions`, `YTD Revenue` — each with current value, sub-label, coloured top border.
  - "Arrivals & Departures This Week" panel — green rows for arrivals (with `Q` / `S` level pill = Quintessential/Signature), grey rows for departures. Clicking a row jumps to `ConciergeExperiencePage` with `bookingRef`.
  - "Concierge Actions Required" panel — alert cards with `arriving_soon | waiting_client | payment_pending | new_booking | waiting_client` types and a "View all →" link to Concierge overview.
  - "Revenue Trend (6 months)" bar chart with YTD / Avg Booking / Occupancy footer stats.
  - "Outstanding Payments" panel with overdue chip, click-through to Finance.
  - "Open Quotes Pipeline" — 5-card grid filterable by stage chip (`All | New Enquiry | Progressing | Quote Sent | Follow-up`) with total pipeline value footer.
- **Spec coverage:**
  - `product-design/02-frontend-design.md §3.1 Operator Dashboard` (lines 146–178) — strongly aligned: arrivals, payment chasers, pipeline, KPIs.
  - `product-design/05-improvements-over-original.md §1 Dashboard becomes useful` (lines 7–12).
- **Departures / new behaviour:**
  - `Concierge Actions Required` panel is **new** beyond the spec — spec mentions "today's arrivals/departures" and "open enquiries", but not a concierge-attention queue.
  - Concierge "Q" / "S" badges on arrival rows imply a `concierge_level` field on Booking (see Domain model gap in §3).

### 2.2 Quotes & Enquiries

- **Purpose:** unified list & detail for the sales pipeline; one record blends enquiry + the quotes built from it.
- **UI elements (list view):**
  - Stage tab bar with counts: `All | New Enquiry | Progressing | Quote Sent | Follow-up` (constant `PIPELINE_STAGES`).
  - Filter row: Show Entries (10/25/50/100), Lead status (`Hot | Warm | Cold | Dead`), Sales person dropdown (`— Unassigned —, Carla Vieira, Fay Dimitrouka, James Okafor, Sofia Martins`), free-text search.
  - Columns: `VC Ref` (e.g. `QVC-3679`), `Name`, `Villa Name`, `Region`, `Enq/Quote Date`, `Sales Person` (editable dropdown in-row), `Holiday Dates`, `Flex?` (`Specific dates | +/- 3 days | +/- 7 days | Flexible` with colour), `Stage`, `Lead Status` (with `Dead reason` sub-dropdown: `Found something else | Availability | Chose a different destination | Couldn't get group consensus | Don't know`), Action.
  - Coloured dot per row: green / orange / pink (legend unstated in mockup — interpret as priority).
  - "+ New Quote" CTA.
- **UI elements (detail / `QuoteDetail`):**
  - Client info card with Enquiry type toggle: **Consumer | Agent** (top-right) — the entire form rebinds to either a client search or an agent search.
  - Unified client/agent search (typeahead) — `searchTab: "client" | "agent"` — searches `QE_CLIENTS` or `QE_AGENTS_FLAT` (flat list including sub-agents).
  - Linked contacts panel — fetches family/business contacts (relationships: Spouse, Child, Business…).
  - Client flag checkboxes: `VIP | Repeat | Trade | PA | Nick's friend | Nick's network | Disability | Approach with care | Past issues | Specific preferences | Time waster`.
  - "Live Enquiries" accordion list (per enquiry: ref, received, destination, travel range, adults/children, guests, min/max bed, salesPerson, status `active|new`, notes, source `Previous Customer | Website | …`, flex preference) with N quote versions inside.
  - Each quote: ref `QVC-3708/Q1`, villa, arrive/depart, guests, **quote status** = one of `Draft | Sent | Viewed | Follow Up | Accepted | Deposit Due | Deposit Paid | Booked | Declined | Expired | Cancelled` (palette `QUOTE_STAGES`).
  - **Rate Lookup section** (embedded `RateLookup` component) — large search form: Arrive Date / Arrive Date to / Destination (multi) / Region (multi) / Number of Weeks / Search Specific Date / Guests / Min/Max Bed / Min/Max price / Properties / Feature / Collection / Unbranded Links / "Generate Quotes" button → results panel with property cards, mini-calendars, per-week price cells (`Available | Unavailable | hold-flag`) and "Send Quote" CTA.
  - "New Quote" two-step modal: pick mode = `copy` (duplicate existing quote) | `enquiry` (new quote on an existing enquiry) | `fresh`.
  - Duplicate-quote modal with ref / from / to / dest / villa overrides.
  - Enquiry history (read-only) accordion listing all prior bookings/quotes for the client with the **booked quote** highlighted.
- **Spec coverage:**
  - `workflows/07-enquiry/enquiry-intake.md` (whole file) — the "Live Enquiries" data model matches; spec covers website intake, manual creation, Zoho push.
  - `workflows/07-enquiry/enquiry-management.md` — list/edit/status.
  - `workflows/08-quotation/construction.md`, `lifecycle.md`, `persistence.md`, `transmission.md`.
  - `product-design/02-frontend-design.md §3.10 Quote Builder` (lines 406–436) — the cart-style multi-villa quote.
  - `product-design/02-frontend-design.md §3.11 Enquiry Inbox` (lines 437–461) — calls for kanban; the mockup uses **list + stage tabs**, not a kanban board.
  - `product-design/05-improvements-over-original.md §17 Enquiry pipeline as kanban` — explicitly says kanban; the mockup ignores this and goes list-only.
  - `product-design/04-rest-api-surface.md §2.6 Enquiries` (line 390), `§2.7 Quotations` (line 410).
- **Departures / new behaviour:**
  - **Enquiry + quote are fused in a single detail view** — spec treats them as two separate resources with distinct REST paths (`/enquiries/{id}`, `/quotes/{id}`). The mockup wraps both in one big detail with nested quote versions per enquiry. Open question for product.
  - **"Lead Status" (Hot/Warm/Cold/Dead) and "Dead Reason"** are new fields — not in `01-domain-model.md §Enquiry` (lines 165–183).
  - **"Flex?" field** with values `Specific dates | +/- 3 days | +/- 7 days | Flexible` is implicit only — spec has `EnquiryDateFlex` but not the enum values.
  - **Unified contact/agent enquiry type** is new — spec models Enquiry as having a `guest_id` (Guest cluster, lines 296–302) and optionally an `agent_id` via a separate field; the mockup makes them mutually exclusive via a top-of-form toggle.
  - **Quote statuses `Viewed`, `Follow Up`, `Deposit Due`, `Deposit Paid`** are new vs `workflows/08-quotation/lifecycle.md` (which has `draft | sent | accepted | converted | lost | expired`).
  - **Embedded Rate Lookup form inside the quote detail** is new — spec has Rate Lookup as a separate screen only.
  - **"Unbranded Links"** toggle on rate lookup is implied — drop-shipper / agent-anonymised quotes. Not in spec.

### 2.3 Rate Lookup (standalone page)

- **Purpose:** ad-hoc availability + price search across the inventory; identical component to the embedded one inside Q&E.
- **UI elements:** same as §2.2 above. Destinations list (constant `RL_DESTINATIONS`) covers Greece, Italy, France, Morocco, Spain, Croatia, Portugal, Turkey, Cyprus, Malta; regions map per destination; **Features** (`Pool, Sea View, Beach Access, Private Chef, Tennis Court, Gym, Air Conditioning, Pet Friendly`); **Collections** (`Private Catering, Good for Teenagers, Group Getaways, Secluded, Racket Courts, Walk to Restaurants, The Beach within Reach, Jetty Access, Weddings & Events, Paired Properties, Private Lawn and Party, Romantic Getaways`).
- **Spec coverage:** `workflows/08-quotation/construction.md §Search property options for quote` (line 5), `product-design/02-frontend-design.md §3.4 Property Rates Editor` and §3.10. Rate Lookup as a standalone is **not in the spec**.
- **Departures:** "Send Quote" button at the bottom of the results table implies inline conversion from search → quote without a separate quote-builder step. Spec routes through the quote builder.

### 2.4 Bookings

- **Purpose:** active reservations list.
- **UI elements:**
  - **Status tab bar** (constant `BOOKING_STATUS_TABS` in the bundle): `All | Confirmed | Deposit Paid | Deposit Outstanding | Balance Paid | Balance Outstanding | In Resort | Completed | Cancelled` — each with count badge and colour. Note these are **derived states**, not the underlying booking status enum.
  - 4 stat cards (clickable as quick filters): `Total Bookings | Overdue Deposits | Overdue Balances | Awaiting Deposit`.
  - Filters: search, All regions, All payment statuses (`Deposit paid | Awaiting dep | Dep overdue | Balance paid | Awaiting payment | Balance overdue`), All salespeople, All experience mgrs.
  - "+ New booking" CTA.
  - Columns: `Client`, `Booking No.`, `Salesperson` (avatar+name), `Experience Mgr` (in-row dropdown of EMs, default `Assign…`), `Villa`, `Region`, `Primary Contact`, `Confirmed`, `Dates`, `Finances` — a three-sub-column block: `DEP / BAL / SEC` each with amount, currency symbol, status badge.
- **Spec coverage:**
  - `workflows/09-booking/booking-management.md §List bookings` (line 5–24).
  - `product-design/02-frontend-design.md §3.7 Bookings List` (lines 322–343).
  - `product-design/04-rest-api-surface.md §2.8 Bookings`.
- **Departures / new behaviour:**
  - **Experience Mgr** dropdown column with assign-to-EM in-place; spec mentions "experience manager" only in passing.
  - **Status enum is composite/derived** — `Deposit Paid / Deposit Outstanding / Balance Paid / Balance Outstanding` are computed from `DepositPaymentTrack` / `BalancePaymentTrack` (`01-domain-model.md §7`). The mockup surfaces them as first-class tabs.
  - **`In Resort`** status is **new** — implies a per-day computed state when `arrival ≤ today < departure`. Not in `01-domain-model.md §Booking`.
  - "DEP / BAL / SEC" combined column is a nicer UX than the spec's separate payment views.

### 2.5 Booking Detail

- **Purpose:** the heart of the booking record.
- **UI elements (long scroll, no tabs in this mockup — contrary to spec):**
  - Header: back-link, ref (e.g. `VC3390`), guest name, villa, location, booking status pill (`Booking Underway | Departed | …`), owner status pill (`Owner Confirmed | …`).
  - **Customer Details** section (Title, First, Last, Pref Contact Phone/Email radios, Email + Country Code + Phone, two address lines, town, country, postcode).
  - **Payer Details** section (same shape — implies payer can ≠ guest).
  - **Customer Notes (Internal)** — rich text editor (toolbar with undo/redo/bold/italic/underline/strike, font, size, paragraph dropdown) + a flag grid (same `VIP | Repeat | Trade | PA | Nick's friend | Nick's network | Disability | Approach with care | Past issues | Specific preferences | Time waster`).
  - **Booking Details** — villa card, arrival/departure dates, adults/children, TBC checkbox, Currency, Price, rich-text Booking Summary, rich-text Internal Booking Information, **Concierge Level radio (`Quintessential | Signature`)** with extra "Cost" input when Signature, Booking URL.
  - **Owner Details** (title/name/email/phone/address — read-only-ish).
  - **Villa Details** — Villa Information (RTE) + Further Villa Information (RTE).
  - **Finance Details** — a big green "Client booking" panel with:
    - Villa Cost / **Price Adjustment** (override) / **Discount Villa** with the new "Who absorbs the discount?" radio (`Commission split | VC absorbs in full`) / **Client Total**.
    - 3 boxes: Deposit Amount (% of total), Balance Payment, Security Deposit.
    - **Override Deposit** checkbox revealing Deposit % select (10/20/30/40/50) and Balance Due date.
    - Payment-method radios (`CC – Pre-Auth | BT – Payment`).
    - 3-row payment matrix (Deposit / Balance / Sec Dep) — each with amount, method, due, status badge, and a "Change" checkbox that swaps status for an editable dropdown (per-row option sets — see `PAYMENT_OPTIONS`).
    - **"Net to Owner"** grey panel showing Owner gross − VC commission(20 %) = Net to owner, with sub-breakdown for owner deposit share (30 % of guest deposit) and balance share (70 %), plus "How the discount lands:" explainer.
  - **Notes & Comms** — green "💬 Internal thread for the on-the-ground team (Regional Managers) and the VC office" callout, with author + role + timestamp messages. Regional managers get a green "Regional manager" pill.
  - **Concierge & Experience** — 4 stat cards, service overview chips (Done/Working on it/Waiting on client/Not required/Not started), CTA "Open Experience & Concierge".
  - **Guest Feedback** — pulls from `window.__vcFeedback` store: stat cards (Average score, Status badge, Aspects rated, Replies), aspect breakdown chips, quoted final comment, "Open full feedback →".
- **Status vocabulary observed in `PAYMENT_STATUS_STYLES`:** `Awaiting | Paid | Overdue | Guaranteed | Not req.` (booking-detail simplified) — and `PAYMENT_OPTIONS` per row:
  - Deposit: `Awaiting deposit | Deposit paid`
  - Balance: `Balance due | Balance email sent | Balance overdue | Balance paid`
  - Sec Dep: `Awaiting SD details | SD details received | SD activated | SD deactivated`
- **Spec coverage:**
  - `product-design/02-frontend-design.md §3.8 Booking Detail — Tabbed with Right Rail` (lines 344–381). **The mockup flattens this back to a long scroll instead of the spec's left-tabs + right-rail.** Big departure.
  - `workflows/09-booking/booking-management.md §View booking detail` (line 25).
  - `workflows/09-booking/booking-modification.md`.
  - `workflows/09-booking/payment-schedule.md` — 3-tier payment schedule generation aligns with the 3-row matrix.
  - `01-domain-model.md §DepositPaymentTrack / BalancePaymentTrack / SecurityDeposit` (lines 321–341) — the matrix is a perfect read-out of these.
- **Departures / new behaviour:**
  - **Flat scroll, not tabs + right rail** — direct contradiction of `product-design/02-frontend-design.md §3.8` and `05-improvements-over-original.md §3 Booking detail: monolithic scroll → tabs + right rail` (lines 19–24). The improvement is reverted.
  - **Concierge Level radio (Quintessential / Signature)** on every booking — new field. Not in `01-domain-model.md §Booking` (lines 200–224). Signature has a "Cost" override input — implies a per-booking fee that varies (Quintessential = fully included, Signature = pay-per-booking).
  - **Discount split radio (Commission split / VC absorbs in full)** with live owner-net math — new semantics not in `08-quotation/persistence.md §Apply discount` (line 92).
  - **Payer ≠ Guest** as a first-class duplication of address blocks — spec collapses payer and guest into Guest with an optional billing address.
  - **`SD activated / SD deactivated`** terms — implies the security-deposit pre-auth (`workflows/10-payment/payment-preauth.md` marked `[DISABLED]`) is **re-enabled** in this mockup. Conflict with spec.
  - **Notes & Comms thread with Regional Manager role pill** — see §2.14 (Regional Managers) in this analysis. New entity / role.
  - **"Net to Owner" panel** — new computed view. Spec has commission tracking but no canonical owner-net summary widget.
  - **Guest Feedback panel embedded** — new (the Feedback page itself is new — see §2.13).

### 2.6 Archive Bookings

- **Purpose:** historical bookings imported from a previous system (i.e. pre-system bookings that need to occupy calendar slots but don't need full lifecycle).
- **UI elements:** simple list — `Name | From date | To date | Villa | Adults | Children | Action(delete)`. Search + page size. "+ Add Archive Booking" opens a slim form (Client info, town/country/postcode, address; Arrival/Dep date, Adults/Children, Price, Currency, Villa, Notes).
- **Spec coverage:** `01-domain-model.md §ArchiveBooking` (line 232). Mentioned but minimal.
- **Departures:** the mockup confirms archive bookings are a separate first-class screen, not a tab on the main Bookings list.

### 2.7 Concierge (Overview)

- **Purpose:** the EM's "what needs me today" view across all active bookings.
- **UI elements:**
  - Top tabs: `Active Bookings | Past Bookings`.
  - Header chip: "N new bookings" (highlights `isNew: true` items).
  - 5 stat cards: `Total Active | In Progress | Waiting on Client | Open Payment Lists | Arriving ≤ 30 days`. Each stat card acts as a quick filter.
  - Filters: search, All Managers (`EXP_MANAGERS`), All Regions, Level chip group (`All Levels | Quintessential | Signature`).
  - **Service status grid columns** — 10 fixed services per booking row: `Car | Transfers | Boat | Chef | Grocery | 1st Night | Restaurant | Gifting | Activities | Spa`. Each cell is a coloured dot per `STATUSES` (`not_started | working_on_it | waiting | arranged_independently | not_required | done`).
  - Other columns: `Booking`, `Client`, `Villa / Region`, `Arrives` (with countdown days pill), `Manager`, `Level` (Q/S badge), `Done` (progress %), `Lists` (count + "open"), action "Open →".
  - Footer legend listing all 6 statuses.
- **Spec coverage:** `product-design/02-frontend-design.md §3.14 Concierge Management` (lines 523–540). Spec calls for "list view + per-line cost/margin tracking"; mockup goes further with the service-dot matrix.
- **Departures:**
  - **10 fixed service categories** as columns are new — spec doesn't enumerate them.
  - **6-state status enum** (`not_started`, `working_on_it`, `waiting`, `arranged_ind`, `not_required`, `done`) is new and load-bearing — see §3 Implied data model.
  - Stat-card-as-filter pattern (click "Waiting on Client" to filter the table) is nice UX, not in spec.
  - "New" chip on freshly-imported bookings — implies a `concierge_brief_started_at` or `is_new_to_em` field.

### 2.8 Concierge & Experience (per-booking)

- **Purpose:** the deep workspace for one booking's experience programme.
- **UI elements:**
  - Header: ref, client, villa, region, **concierge level pill**, Exp Mgr name, dates.
  - 6 KPI strip: `Total Value | Client Price | Paid | Awaiting | Services Done | Total Items`.
  - **Tab bar:** `Overview | Payment Lists | Timeline | Post-Stay | Suppliers`.
  - **Overview tab:** "Service Status Board" — a row per service (`Car Hire, Boat & Charter, Private Chef, Nanny / Babysitting, Transfers, Pre-Arrival Grocery, 1st Night Menu, Local Guide & Wine, Restaurant Reservations, Gifting, Activities, Spa & Wellness, Other Requests`), each with the status pill, notes input, items count badge, value sum, expand-row for items. "Add custom service" with colour picker.
  - **Payment Lists tab:** N named lists per booking ("Pre-Arrival", "Week 2 Activities" etc.). Each list has badge `open | payment_requested | paid`, requested-at / paid-at timestamps, line items table (`Service | Description | Supplier | Date | Qty | Cost Price | Total | Client Price (margin) | Status (pending/confirmed/cancelled) | Notes`). Actions: "Request Payment" (locks list), "Export PDF", "Mark Paid", "View Invoice". "+ New Payment List".
  - **Timeline tab:** grid of stay days (1 column per night) showing items scheduled per day, coloured by service.
  - **Post-Stay tab:** locked-warning banner, General Stay Notes (textarea), **Client Preferences & Insights** (saves to client profile), "What went well?" tag picker (preset tags), Save / Print buttons.
  - **Suppliers tab:** filtered to booking country with "All-countries / universal" fallback. Columns: `Name | Service | Countries | Contact | Phone | Email | Commission | Notes`. Inline add-supplier form with country chips picker (`France | Greece | Italy | Kenya | Morocco | Spain | UK`).
- **Spec coverage:**
  - `workflows/09-booking/concierge.md §Save concierge service add-ons` (line 5) — covers add-on lines; the mockup is a massive expansion.
  - `workflows/09-booking/concierge.md §Request concierge payment from guest` (line 41) — matches the "Request Payment" button on a list.
  - `product-design/02-frontend-design.md §3.14 Concierge Management`.
  - `product-design/05-improvements-over-original.md §14 Concierge: per-line state, supplier cost, margin tracking` (lines 92–97).
- **Departures / new behaviour:**
  - **5-tab UI** is much more elaborate than spec (`product-design/02-frontend-design.md §3.14`).
  - **Item-level status** (`pending | confirmed | cancelled`) — new field beyond `01-domain-model.md §ConciergeLineItem` (line 225).
  - **Payment List as a first-class entity** grouping items — spec models items at the booking level only. Adds: `name`, `status (open/payment_requested/paid)`, `requested_at`, `paid_at`, `items[]`.
  - **List → PDF export → Mark Paid lifecycle** is concretely workflow-y.
  - **Per-supplier commission %** stored on supplier record.
  - **Suppliers tagged by country** — implies a Supplier↔Country many-to-many.
  - **Custom services** can be added per booking with their own colour — implies a per-tenant or per-booking dynamic service catalogue beyond the seeded list.
  - **"What went well?" debrief tags** — saved at booking level, feed into a global tag pool managed in Settings → Concierge Settings → Debrief Tags.
  - **Stay Timeline** — visual day grid with items dropped on dates. New.

### 2.9 Availability

- **Purpose:** single-villa, 12-month grid with status overlays + an "Add dates" modal for range entry.
- **UI elements:**
  - Dark top-bar: Villa Search (searchable dropdown), URL/Text radio + URL input, + (add), eye, timestamp.
  - Bottom toolbar: "Add dates" green button, legend (`Available | On Hold | Booked / Booked VC | Stop Sale | Available (again)`), helper text "Click any day to cycle status · Split cells = same-day turnaround".
  - 12 month grid (4 × 3) starting March 2026. Each day is a coloured square; **split-cell diagonal** for same-day turnover (checkout AM, check-in PM).
  - Click-to-cycle: `available → onHold → booked → bookedVC → stopSale → availableAgain → available`.
  - **Add Dates modal** — 3-month strip, radio for status, click start → click end → adds pending range → optionally add more → Save batches all ranges.
- **Spec coverage:**
  - `workflows/06-availability/calendar-view.md` — single-villa calendar.
  - `workflows/06-availability/blocks-and-changeover.md` — block creation.
  - `workflows/06-availability/booking-status-transitions.md` — status transitions on booking confirm/cancel.
  - `product-design/02-frontend-design.md §3.6 Availability — Single Villa Calendar (familiar)` (lines 306–321).
  - `product-design/02-frontend-design.md §3.5 Availability — Multi-Villa Timeline (the improved view)` (lines 274–305). **The mockup does NOT implement the multi-villa timeline view** — only the legacy single-villa one. A multi-villa popup *does* appear via the Quick View Rates modal on Properties (see §2.11), but it's not a primary screen.
  - `product-design/05-improvements-over-original.md §6 Calendar: single-villa only → multi-villa timeline as primary` (lines 37–42). **Mockup reverts this improvement** in the main Availability screen.
- **Departures:**
  - **`bookedVC` distinct from `booked`** — implies a "managed by VC" vs "external" booking marker. Both share visual colour but the click cycle treats them as separate states. Not in `01-domain-model.md §AvailabilityRecord` (line 254).
  - **Split-cell same-day turnaround** at boundaries — concretely UX'd. Spec mentions changeover-day rules but not the diagonal visual.
  - **"Available (again)" status** is distinct from "Available" — used to mark dates released after a cancellation. New.
  - **URL/Text input** at top — appears to be a supplier portal link the staff opens to verify availability. Not in spec.

### 2.10 Properties (list)

- **Purpose:** the master inventory list.
- **UI elements:**
  - Filters: Country / Region / Group (all `select`s).
  - Search, Show Entries (10/25/50/100).
  - Top-right CTAs: **`Sync to Web`** (bulk) and **`+ Add Property`**.
  - Columns: Action button strip (Edit + Quick View Rates), Display Name (+ Changeover badge if non-Sat: `Sun` amber, `Fri` blue, `Open` green, `Flex` green), Name (internal name distinct from display), Country, Region, Updated At, Updated By.
  - **Quick View Rates modal** — full-screen overlay grid: property rows × 10 weekly columns (Saturdays from current month). Cells show price or status text (`Booked | Booked VC | Stop Sale | €rate | Enquire for Availability`). Month navigator (prev/next). Legend with 5 statuses.
- **Spec coverage:**
  - `product-design/02-frontend-design.md §3.2 Properties List` (lines 179–199).
  - `workflows/03-catalog/property-master.md`.
- **Departures:**
  - **Display Name vs Name** as separate fields — implies two different name fields on Property (a public marketing name and an internal name). Spec has one `name` field (`01-domain-model.md §Property` line 54).
  - **Changeover-day badge** is a nice surface for the `ChangeOverRule` (`01-domain-model.md §ChangeOverRule` line 117).
  - **Quick View Rates modal as a sibling to Properties list** is a great approximation of `product-design/02-frontend-design.md §3.5 Availability — Multi-Villa Timeline` but only by saturday-week and only by hand-rolled cellular fake data — not the primary Availability screen.
  - **Group filter** implies a `Property.group` field. `01-domain-model.md §PropertyGroup` exists (line 76); the mockup just exposes it.

### 2.11 Property Detail

- **Purpose:** master record edit for a single villa.
- **UI elements:**
  - Header: back link, Display Name, Property #ID, **`Active` status pill**, "View on website", **"Sync to web"**, "Delete Property", "Save Changes".
  - Sidebar sub-tabs (left, in main app sidebar): **Overview, Information, Rates, Finance, Availability, Rooms, Features, Nearby, Contacts, Settings, Images, Descriptions** (13 entries — note: `Bookings` is in `SUB_NAV` line 9127 but not in `_PROP_TABS` line 13293 — actually it's not rendered in the sidebar list, even though `TabBookings` exists at line 9060).
  - Each tab is a self-contained editing form. Notable tabs:
    - **Rates** — has a `RateForm` modal with arrival/departure date validation against seasons (`rangeWithinSeasons`), seasonal logic, `OccupancyPricing` toggle, multiple price tiers.
    - **Finance** — has `CommissionPanel`, `WebsitePricing`.
    - **Availability** — per-property version of the 12-month grid (with `availDaysInMonth` / `availSolidOrSplit` helpers).
    - **Rooms** — `BedroomForm` modal, `LinkedVillasPanel` for paired villas.
    - **Features** — `FeatureTable` + `FeaturePickerModal` (browse by category + add custom).
    - **Nearby** — `NearbyForm` + `NearbyTable` per POI category (airport, beach, train, ski lift, town, restaurant, hospital).
    - **Contacts** — `ContactForm` modal.
    - **Settings** — `ConfirmModal` patterns.
- **Spec coverage:**
  - `product-design/02-frontend-design.md §3.3 Property Detail — Tab Grouping` (lines 200–229).
  - `product-design/02-frontend-design.md §3.4 Property Rates Editor` (lines 230–273).
  - `workflows/03-catalog/property-master.md`, `property-rooms.md`, `property-features.md`, `property-nearby.md`, `property-imagery.md`, `property-finance.md`.
  - `product-design/05-improvements-over-original.md §2 Property detail collapses 14 tabs into 6` (lines 13–18). **The mockup has 13 tabs** — not the proposed 6. Direct departure.
- **Departures:**
  - **13 tabs instead of the spec's recommended 6** — contradicts `05-improvements-over-original.md §2`. The mockup is closer to the legacy 14-tab layout.
  - **"Sync to web" per-property** in addition to a global "Sync to Web" on the list — implies per-property `last_synced_at` + dirty-flag tracking, beyond `workflows/11-integrations/public-website-sync.md`.
  - **Linked Villas Panel** ("paired properties") — partly covered by `01-domain-model.md §PropertyAlternative` (line 114) but the mockup uses it for grouping villas that rent together (e.g. "Soukia Estate").
  - **`Active` status pill** in header implies an explicit lifecycle enum on Property (e.g. `Draft | Active | Archived`) — matches the CLAUDE.md project rule of using status enums.

### 2.12 Clients

- **Purpose:** consumer (B2C) directory.
- **UI elements:**
  - List view: type chips `VIP | Repeat | Trade` as filters, search, columns `Name | Email Address | Telephone | Quoted regions (chips) | Booked regions (chips) | Client Type (badges)`.
  - Detail view: `Client Information` section (title, name, pref contact, email, country code, phone, address), 11-flag grid (`vip | repeat | trade | pa | nicksFriend | nicksNetwork | disability | approachWithCare | specificPreferences | pastIssues | timeWaster`).
  - **Connected Contacts** subsection — relations dropdown (`Sister | Brother | Wife | Husband | Partner | Friend | Colleague | PA | Other`); inline add row.
  - **Previous Quotes** subsection — table with Quote ref, Region, From-To, Weeks, Guests, action eye → opens `QuotationsEnquiriesPage`.
  - **Previous Bookings** subsection — Ref, Region, From, action.
  - Delete confirmation modal.
- **Spec coverage:**
  - `01-domain-model.md §Guest` (line 296).
  - `product-design/04-rest-api-surface.md §2.17 Guests / Clients` (line 624).
- **Departures:**
  - **11-flag client profile** is much richer than spec's `Guest` (which has 8 PII fields and not much else).
  - **`Trade` flag** overlaps semantically with the Agent record — i.e. a guest can be "trade" without being a formalised Agent. New behaviour.
  - **"Connected Contacts" with relationship enum** — implies a `GuestRelationship` model (self-referential or to a Contact). Not in `01-domain-model.md`.
  - **"Quoted regions" and "Booked regions" chips** on the list view — derived/cached, but mockup makes them prominent. Implies a per-client analytics rollup.

### 2.13 Agents

- **Purpose:** B2B sales partner directory.
- **UI elements:**
  - List columns: `Name / Company | Email | Telephone | Type` (Individual / Company badge; if Company also shows "N sub-agents" badge).
  - Detail: **Agent type toggle (Individual / Company)** at the top — the form rebinds.
  - Individual form: Company, Agent nick name, Title, First/Last, Country Code, Phone, Email, address, Notes.
  - Company form: Company Name + Agent Nick Name, **Lead Contact** subsection (title/name/phone/email), **Address**, **Sub-Agents** subsection — inline form to add (First/Last/Phone/Email/Enter) + table of added sub-agents with delete.
  - Delete confirmation.
- **Spec coverage:**
  - `01-domain-model.md §Contact` cluster (line 274 onwards) — agents are modelled as a Contact with role=agent.
  - `workflows/05-directory/contact-roles.md`.
- **Departures:**
  - **Agent type Individual vs Company as a first-class toggle** with **Sub-Agents** as a sub-collection — this is a real structural difference from "Contact with a role". The spec models Agent as Contact + role; the mockup models Agent (Company) → Sub-Agents (1:N), separate from Contacts. See §3.
  - **"Agent nick name"** field is new — used to refer to the agent in client-facing materials.
  - Mockup has a **separate "Agents" sidebar entry** distinct from "Suppliers" (which is the existing Contacts page) — confirming the spec's open question (in `workflows/07-enquiry/README.md §Open design questions for the Django redesign`, lines 33+) about whether agents are first-class.

### 2.14 Suppliers (= `ContactsPage`)

- **Purpose:** in-resort vendor + owner / villa-manager directory. Confusingly, the page label is **Suppliers** but the underlying `ContactsPage` component still uses `Contacts` terminology in some places.
- **UI elements:**
  - List columns: `Name | Email Address | Telephone | Properties (chip per linked property)`.
  - Detail form: Title, First/Last, Company, Address Lines, Email, Country Code, Tel, Preferred Method (`Not specified | Email | Phone | WhatsApp`), Group(s) multi-select (constants: `Soukia Estate, Villa Soros, Maia, Cavo Aryatis, Kerasia Olive Press`), Website URL, Notes.
  - **Properties subsection** — add property from typeahead, table of linked properties with `Display Name | Name | Country | Role | Action`. Role is a multi-select dropdown (`PropRoleDropdown`) with options: `Owner | Agent | Villa Admin | Villa Manager | Management Company`.
- **Spec coverage:**
  - `workflows/05-directory/contact-records.md` (full file).
  - `workflows/05-directory/contact-roles.md` (line 1).
  - `workflows/05-directory/contact-property-assignment.md`.
  - `product-design/02-frontend-design.md §3.13 Contact Detail — Simplified Permissions` (lines 494–522).
- **Departures:**
  - **Page is labelled "Suppliers"** but the underlying entity is the legacy `Contact` with roles `Owner | Agent | Villa Admin | Villa Manager | Management Company`. Confusing dual nomenclature — see §5 Conflicts.
  - **Note:** there's *also* a separate `Suppliers` concept inside Concierge for in-resort vendors (chef, transfers, car hire), managed in **Settings → Concierge Settings → Suppliers** and per-booking on the **Concierge Suppliers tab**. Two different concepts share the word "Supplier". This needs renaming.

### 2.15 Finance & Invoicing

- **Purpose:** booking-level money pipeline and revenue analytics.
- **UI elements:**
  - 3 tabs: `Invoices | Outstanding | Revenue`.
  - 5 summary cards: Total Pipeline / YTD Received / Outstanding / Overdue / Avg Booking Value.
  - **Invoices tab:** search, status filter chips (`All`, `Deposit Due`, `Deposit Received`, `Balance Due`, `Fully Paid`, `Overdue`, `Cancelled`, `Draft` — see `PAYMENT_STATUSES`). Table columns: expand, Booking, Client, Property, Check-in, Total Value, Deposit (amount + paid-date or "Pending"), Balance (amount + paid-date or "⚠ Overdue"), **Status pill (dropdown — change in place)**, Notes (click-to-edit inline), Action ("Concierge").
  - Expand-row reveals: Booking Breakdown (Rental + Concierge), Payment Schedule (Deposit %, Balance), Booking Details (check-in/out, nights, guests, salesperson, agent), **Change Status** vertical button list.
  - **Outstanding tab:** alert banner + same table filtered to non-paid, with **"Mark <next status>"** quick action per row.
  - **Revenue tab:** Revenue by Country bar chart + Revenue Summary list.
- **Spec coverage:**
  - `workflows/09-booking/payment-schedule.md`.
  - `workflows/10-payment/payment-collection.md`.
  - `product-design/02-frontend-design.md §3.12 Payments View (per booking)` (lines 462–493).
  - `product-design/05-improvements-over-original.md §11 Three payment tracks modelled explicitly` (lines 70–75).
- **Departures:**
  - **Concierge Value is a separate line on the invoice** (rental + concierge = total) — implies the concierge total is invoiced alongside the villa, not just on payment lists. Conflict with §2.8 — see §5.
  - **In-place status dropdown on every invoice row** — direct-edit pattern; spec recommends edits via Booking Detail.
  - **"Notes" inline-edit per invoice** — implies a per-booking-finance free-text notes field (separate from Booking.notes).
  - **Status-card filter** for `Overdue` highlights — colour-only at row level.

### 2.16 Feedback

- **Purpose:** post-stay guest feedback inbox + replies.
- **UI elements:**
  - 4 summary cards: Total feedback / Awaiting response / Average score / Low-score alerts.
  - Filters: search, All statuses (`All | New | Acknowledged | Responded | Closed`), All scores (`High 4.5-5 | Mid 3.5-4.4 | Low <3.5`), Newest first / Highest score / Lowest score.
  - List columns: `Submitted | Booking (ref → booking detail) | Guest & property | Score (stars) | Status (badge) | Assigned`.
  - **Detail view per feedback:**
    - Header: guest, property, booking ref link, party size, stay dates, submission timestamp + email, Status badge, Assigned-to, **"Prize draw entry" pill** if opted in.
    - 4 stat cards: Average score, Aspects rated, Comments count, Replies in thread.
    - **Aspect ratings list** — variable per booking. Seen aspects: `overall | villa | concierge | comms | transfers | carhire | chef | grocery | boat | spa`. Stars + free-text comment per aspect.
    - **"Anything else?"** final free-text panel.
    - **Response thread** — team vs guest messages, "Send reply" textarea, status auto-advances `new/acknowledged → responded` on send.
    - Footer status workflow: `New → Acknowledged → Responded → Closed`, "Mark as <next>" CTA.
- **Spec coverage:** **None.** No workflow doc, no domain model entity, no API endpoint for feedback. The entire screen and its data model are net-new.
- **Departures / new behaviour:**
  - **Whole module is new.** See §3 for the implied data model and §6 for the open questions.
  - Mention of "post-stay email triggers automatically the day after departure" in `BookingDetailPage` "No feedback yet" empty state — implies an automation/scheduler.

### 2.17 Settings

A two-level page: section sidebar (left) + content (right). Sections (constant `subNavItems`):

1. **Countries** — list with `Name | A2 | A3 | Tax Rate % | Enable`. Inline add + edit row. **Sub-feature: click a country to reveal a Regions sub-list** (with inline add, delete with confirm).
2. **Regional Managers** — keyed by `"Country|Region"`. Per region, lead + backup users with phone. New section — see §3.
3. **Currencies** — `Euro(€)`, `Pound sterling(£)`, `Dollar($)`, add new (name/code/symbol/symbolAfter). Set-default radio.
4. **Config** — General tab dominant. Fields: Site Name, URL, API key.
5. **Users** — full CRUD modal: email, name, **Admin Yes/No**, **roles** (`experience | admin | regional-manager`), 2FA Required, 2FA Method, mobile, mobile verified, enabled, per-user SMTP config (server/port/TLS/auth/username/password). See `USERS_DATA` (search the bundle for `USERS_DATA`).
6. **Features** (= property amenities) — CRUD with icon upload, categories multi-select, "in lookup" flag.
7. **Property Defaults** — `PropertyDefaultsPanel` — defaults for new properties.
8. **Collections** — `COLLECTIONS_DATA` ("Private Catering", "Good for Teenagers" etc.) with description + villa mapping per collection.
9. **Property Groups** — group CRUD (used by Group filter on Properties list).
10. **Concierge Settings** — major sub-area with own tabs: **Services | Standard Items | Suppliers | Concierge Levels | Payment Template | Debrief Tags**.
   - **Services tab:** the 13 master services (Car Hire, Boat & Charter, Private Chef, Nanny / Babysitting, Transfers, Pre-Arrival Grocery, 1st Night Menu, Local Guide & Wine, Restaurant Reservations, Gifting, Activities, Spa & Wellness, Other Requests) — each with colour and active toggle.
   - **Standard Items tab:** per-service pre-populated item list (e.g. Car: `Economy Car, Luxury Car, SUV / 4x4, …`).
   - **Suppliers tab:** global supplier directory with name/service/contact/phone/email/commission/notes/countries.
   - **Concierge Levels tab:** the 2 levels (Quintessential, Signature) with description + included-features bullets — editable.
   - **Payment Template tab:** company name + address, bank details, footer text, VAT — used to render the per-list PDF.
   - **Debrief Tags tab:** the global pool of "What went well?" tags.
11. **Import** — see §2.18 (rendered as its own page rather than a Settings panel, but listed under Settings in sidebar).

- **Spec coverage:**
  - `product-design/02-frontend-design.md §3.16 Settings Screens` (lines 551–558).
  - `workflows/02-administration/geographic-taxonomy.md` (countries / regions).
  - `workflows/02-administration/financial-taxonomy.md` (currencies / tax).
  - `workflows/02-administration/product-taxonomy.md` (features / collections / groups).
  - `workflows/02-administration/system-configuration.md` (config).
  - `workflows/01-identity/user-administration.md` (users).
- **Departures:**
  - **Regional Managers as a settings section** — net new. See §2.14 and §3.
  - **Concierge Settings sub-area is a whole secondary settings panel** — net new.
  - **Per-user SMTP credentials** — implies outbound mail can be sent on behalf of individual staff users (so the guest sees mail from sophie@villacollective.com directly). Spec has `workflows/11-integrations/email-delivery.md` but doesn't model per-user SMTP.
  - **Property Defaults** as a section — implies a global defaults document that new properties inherit from. Useful but new.

### 2.18 Import (CSV import wizard)

- **Purpose:** bulk-import properties from a CSV with field mapping, savable as presets.
- **UI elements:**
  - **Saved CSV mappings** strip — preset cards with name, description, column count, last-used date, "+ Save current as preset", delete preset.
  - **Upload CSV** drag-and-drop zone.
  - **Field mapping** table — for each CSV column, a typeahead **SearchableMappingSelect** mapping to one of ~100 VC system fields, grouped by section: `General | Seasons & rates | Finance | Availability | Rooms | Features | Nearby | Settings | Images | Descriptions`. Skip option to ignore a column.
  - **Preview & import** modal — per-property checkbox list with bulk select-all, summary stats, Cancel / Import.
- **Spec coverage:** mentioned only in `workflows/03-catalog/property-rooms.md §Bulk import rooms from CSV` (line 62) — for rooms specifically. **Whole-property CSV import is new.**
- **Departures / new behaviour:**
  - **Mapping presets** stored per-source ("Standard villa-export CSV", "Boukari spreadsheet") with full mapping → implies a `CsvImportPreset` model.
  - **VC catalogue of ~100 target fields across 10 sections** is the de facto importable shape of Property. Useful artefact for the data migration team.

---

## 3. Implied data model additions

Fields and entities the mockup uses that are not (or are only weakly) modelled in `product-design/01-domain-model.md`.

### 3.1 On `Booking`

- **`concierge_level`** — enum `Quintessential | Signature`. Drives EM workflow and per-list pricing. (See `Booking` lines 200–224 in `01-domain-model.md` — no such field.)
- **`signature_cost`** — money, present only when `concierge_level = "Signature"`.
- **`discount_split`** — enum `commission_split | vc_absorbs_full`. Drives owner-net calculation when a discount is applied. New.
- **`booking_status`** *display value* — the mockup's status tabs (`Confirmed | Deposit Paid | Deposit Outstanding | Balance Paid | Balance Outstanding | In Resort | Completed | Cancelled`) are computed states. Spec has `Booking.status` (`hold | provisional | confirmed | departed | cancelled`) — the mockup's mapping needs nailing down.
- **`is_new_to_em`** / `concierge_brief_started_at` — used by the "New" pill in Concierge Overview.
- **`internal_note_thread`** / **`team_comms_thread`** — the Notes & Comms thread on Booking Detail is a thread of `{ author, role, ts, text }`. New.

### 3.2 On `Quotation`

- **Quote sub-status** = `Draft | Sent | Viewed | Follow Up | Accepted | Deposit Due | Deposit Paid | Booked | Declined | Expired | Cancelled` — `Viewed`, `Follow Up`, `Deposit Due`, `Deposit Paid`, `Cancelled` are new vs `workflows/08-quotation/lifecycle.md`.
- **`viewed_at`** — implied by `Viewed` status (probably populated by email-tracking pixel or PDF view).
- **Linked enquiry**: an Enquiry has 1:N versioned quotes. Spec models this loosely; mockup makes it concrete (`liveEnqQuotesMap`).

### 3.3 On `Enquiry`

- **`lead_status`** — enum `Hot | Warm | Cold | Dead`. Net new.
- **`dead_reason`** — enum (`Found something else | Availability | Chose a different destination | Couldn't get group consensus | Don't know`). Net new.
- **`flex`** — enum `Specific dates | +/- 3 days | +/- 7 days | Flexible`. (Spec has the field name `dates_flex` in `01-domain-model.md §Enquiry`, line 165 — but doesn't enumerate the values.)
- **`enquiry_type`** — `consumer | agent` (mutually exclusive).
- **`source`** — enum (`Previous Customer | Website | …`). The spec has `Enquiry.source` but doesn't enumerate.

### 3.4 New `ConciergePaymentList` entity

A list of concierge line items per booking, with its own lifecycle:

```
ConciergePaymentList
  - id
  - booking_id (FK)
  - name (e.g. "Pre-Arrival", "Week 2 Activities")
  - status: open | payment_requested | paid
  - requested_at, paid_at, requested_by, paid_by
  - items: ConciergeLineItem[]  (existing entity, line 225)
```

The existing `ConciergeLineItem` would need to gain:
  - `payment_list_id` FK
  - `item_status` enum `pending | confirmed | cancelled`
  - `client_price` (margin, separate from cost)
  - `scheduled_date` (date the service happens on the stay — used by Timeline)
  - `supplier_id` FK
  - `notes`

### 3.5 New `ConciergeService` master + `StandardItem` sub-list

The 13 services are configurable in Settings → Concierge Settings:

```
ConciergeService
  - id, label, colour, active, sort_order

StandardItem
  - id, service_id (FK), description, sort_order
```

Plus a **custom service per booking** — implies `ConciergeService.is_custom` and an optional `booking_id` scope on custom rows.

### 3.6 New `Supplier` entity (≠ Contact)

The "Suppliers" used inside Concierge are distinct from the people-`Contact` records:

```
ConciergeSupplier
  - id, name, service_id (FK, "primary service")
  - contact_name, phone, email
  - commission_percent (decimal)
  - notes
  - countries (M2M)
```

Currently the mockup stores them globally (`window.__vcSuppliers`). The Settings → Concierge Settings tab is the master CRUD.

### 3.7 New `RegionalManager` / `RegionAssignment` entity

```
RegionAssignment
  - id, country (FK Country), region (FK Region)
  - user_id (FK User), phone, role: lead | backup
  - (unique together: country, region, user_id, role)
```

The Notes & Comms thread on Booking Detail reads from this — anybody on the booking's region with `lead` or `backup` role can post and is tagged "Regional manager".

### 3.8 New `Feedback` cluster

This is the biggest greenfield model:

```
Feedback
  - id, booking_id (FK)
  - submitted_at, submitted_by (email)
  - status: new | acknowledged | responded | closed
  - assigned_to (FK User)
  - avg_score (computed)
  - prize_opt_in (bool)
  - final_comment (text)

FeedbackAspect
  - id, feedback_id (FK)
  - aspect_key: overall | villa | concierge | comms | transfers | carhire | chef | grocery | boat | spa | …
  - title (string — varies per booking, e.g. "Villa Elysian" instead of "The villa")
  - score (int 1-5)
  - comment (text, optional)

FeedbackReply
  - id, feedback_id (FK)
  - from: team | guest
  - author_name, author_role (or FK user)
  - ts, text
```

The aspect keys vary per booking (e.g. some bookings include `carhire`, others don't). Implies a per-stay configurable feedback template — probably driven by which concierge services were active on the stay.

### 3.9 On `Property`

- **`display_name` distinct from `name`** — two fields. Spec has one `name`.
- **`group`** FK to PropertyGroup (already in spec).
- **`changeover_day`** — enum `Sat | Sun | Fri | Open | Flex`. Spec's `ChangeOverRule` is a separate entity; mockup compresses to a per-property field.
- **`last_synced_to_web_at`** — implied by Sync to Web button.

### 3.10 On `Client` / `Guest`

- **`flags`** — 11-bit struct (`vip, repeat, trade, pa, nicksFriend, nicksNetwork, disability, approachWithCare, specificPreferences, pastIssues, timeWaster`). Spec has no such field set.
- **`connected_contacts`** — M2M to other people with a `relationship` label (`Sister | Brother | Wife | Husband | Partner | Friend | Colleague | PA | Other`).

### 3.11 New `Agent` entity (separate from Contact)

```
Agent
  - id
  - type: individual | company
  - company (string), nick_name (string)
  - title, first_name, last_name (lead contact for company)
  - email, country_code, phone, address fields
  - notes

SubAgent
  - id, agent_id (FK, must be type=company)
  - first_name, last_name, phone, email
```

Spec models agents as Contact + role; mockup separates them.

### 3.12 New `CsvImportPreset` entity

```
CsvImportPreset
  - id, label, description
  - columns: string[] (the expected CSV header)
  - mapping: { csv_column: vc_field, ... }
  - last_used_at, created_by
```

### 3.13 New `User`-level fields

- 11 fields shown in the user-edit modal: `admin (Yes/No)`, `roles[]` (`experience | admin | regional-manager`), `twoFARequired`, `twoFAMethod`, `mobileNo`, `mobileVerified`, `enabled`, `smtpAddress`, `smtpPort`, `smtpTLS`, `smtpAuthRequired`, `smtpUsername`, `smtpPassword`. Spec covers most via `01-domain-model.md §User` (line 303) but the **per-user SMTP credentials block** is new.

### 3.14 New `ConciergeDebriefTag` entity

Global pool of tags used in "What went well?" picker. Settings-managed.

---

## 4. Implied API surface additions

Endpoints the mockup implies but `product-design/04-rest-api-surface.md` does not list.

### 4.1 Feedback

- `GET /feedback?status=&score=&q=&sort=`
- `GET /feedback/{id}`
- `POST /feedback/{id}/reply` { text } → returns updated thread + auto-advances status
- `POST /feedback/{id}/transition` { new_status }
- `POST /feedback/{id}/assign` { user_id }
- `POST /bookings/{ref}/feedback` (intake from guest portal — bypasses staff auth)
- `GET /feedback/templates/{booking_id}` — returns the per-booking aspect list

### 4.2 Concierge Payment Lists

- `GET  /bookings/{id}/concierge/payment-lists`
- `POST /bookings/{id}/concierge/payment-lists` { name }
- `PATCH /bookings/{id}/concierge/payment-lists/{list_id}` { name }
- `DELETE /bookings/{id}/concierge/payment-lists/{list_id}` (only when open)
- `POST   /bookings/{id}/concierge/payment-lists/{list_id}/request-payment` → locks list
- `POST   /bookings/{id}/concierge/payment-lists/{list_id}/mark-paid`
- `GET    /bookings/{id}/concierge/payment-lists/{list_id}/pdf` (PDF render)
- `POST/PATCH/DELETE /bookings/{id}/concierge/payment-lists/{list_id}/items` — line items move with the list

These are *not* in `product-design/04-rest-api-surface.md §2.9 Concierge Line Items` (line 496), which models items flat on the booking only.

### 4.3 Regional Managers

- `GET /regions/{country}/{region}/assignments`
- `POST /regions/{country}/{region}/assignments` { user_id, phone, role }
- `DELETE /regions/{country}/{region}/assignments/{id}`
- `POST /bookings/{ref}/notes` (the team-comms thread — different from internal `BookingNote`)

### 4.4 Suppliers (concierge vendors)

- `GET /concierge/suppliers?service=&country=`
- `POST /concierge/suppliers`
- `PATCH /concierge/suppliers/{id}`
- `DELETE /concierge/suppliers/{id}`

### 4.5 Agents

- `GET /agents` / `GET /agents/{id}` / `POST` / `PATCH` / `DELETE`
- `POST /agents/{id}/sub-agents` { firstName, lastName, phone, email }
- `DELETE /agents/{id}/sub-agents/{sub_id}`
- `GET /agents/search?q=` — used by the unified client/agent search on the quote detail.

### 4.6 CSV Import

- `POST /import/properties/preview` (multipart: file + mapping) → returns preview rows + per-row issues
- `POST /import/properties/commit` { preset_id, file_id, selected_ids }
- `GET / POST / DELETE /import/presets`

### 4.7 Property — Sync to Web

- `POST /properties/{id}/sync-to-web`
- `POST /properties/sync-to-web` (bulk)
- `GET  /properties/{id}/sync-status`

### 4.8 Booking — discount split & owner-net preview

- `POST /bookings/{ref}/calculate-owner-net` { adjustment, discount, discount_split } → returns net-to-owner breakdown (rather than computing in the SPA).
- `POST /bookings/{ref}/concierge-level` { level, signature_cost? }

### 4.9 Feedback aspects per booking

- `GET /bookings/{ref}/feedback-template` — returns the aspect keys that should be solicited from this guest (depends on which concierge services were live).

---

## 5. Conflicts with existing specs

Places where the mockup contradicts a deliberate choice in the spec — these need an explicit decision.

### 5.1 Booking Detail is a flat scroll, not tabs + right rail

- Spec: `product-design/02-frontend-design.md §3.8 Booking Detail — Tabbed with Right Rail` (lines 344–381) — calls for left-side tabs (`Summary, Finance, Concierge, Comms, History, Audit`) and a right rail with quick stats / status / actions.
- Spec doubles down in `product-design/05-improvements-over-original.md §3` (lines 19–24) — explicitly listed as an improvement over the legacy single-page-scroll layout.
- **Mockup:** one long top-down scroll — Customer / Payer / Notes / Booking / Owner / Villa / Finance / Notes & Comms / Concierge / Feedback. Reverts the spec's improvement.

### 5.2 Property Detail has 13 tabs, not the spec's 6

- Spec: `product-design/05-improvements-over-original.md §2 Property detail collapses 14 tabs into 6` (lines 13–18). Suggested 6 groups: Overview / Pricing / Inventory / Content / Operations / Access.
- **Mockup:** 13 tabs (Overview, Information, Rates, Finance, Availability, Rooms, Features, Nearby, Contacts, Settings, Images, Descriptions, + Bookings is present in code but not in nav). Reverts the spec's consolidation.

### 5.3 Availability primary view is single-villa, not multi-villa timeline

- Spec: `product-design/02-frontend-design.md §3.5 Availability — Multi-Villa Timeline (the improved view)` (lines 274–305) — wants this as the primary view. `§3.6` (lines 306–321) keeps single-villa as secondary.
- Spec: `product-design/05-improvements-over-original.md §6` (lines 37–42) — single-villa-only is explicitly called a legacy issue.
- **Mockup:** Availability page is single-villa-only. The closest thing to a multi-villa timeline is the Quick View Rates modal on Properties — which is read-only and saturday-week granularity.

### 5.4 Enquiry pipeline is list-with-tabs, not a kanban

- Spec: `product-design/05-improvements-over-original.md §17 Enquiry pipeline as kanban` (lines 115–120). Spec calls for a board view.
- Spec: `product-design/02-frontend-design.md §3.11 Enquiry Inbox` (lines 437–461) — calls for kanban + table modes.
- **Mockup:** list with stage tab bar only. No board mode.

### 5.5 No global Cmd-K command palette

- Spec: `product-design/02-frontend-design.md §6.2 Command Palette (Cmd-K)` (lines 683–692) — net-new ergonomic improvement.
- Spec: `product-design/05-improvements-over-original.md §8 Global search (Cmd-K palette) — entirely new` (lines 49–54).
- **Mockup:** none.

### 5.6 No Reports hub

- Spec: `product-design/02-frontend-design.md §3.15 Reports` (lines 541–550). Listed as a primary screen.
- **Mockup:** no Reports page. Revenue analytics is folded into Finance → Revenue tab only.

### 5.7 Security Deposit pre-auth re-enabled

- Spec: `workflows/10-payment/payment-preauth.md §Pre-authorise security deposit hold` is marked `[DISABLED]` at file level (line 1).
- **Mockup:** Booking Detail has `SD activated / SD deactivated` payment statuses in `PAYMENT_OPTIONS` (`Sec Dep` row, line ~3152), implying the pre-auth lifecycle is live. Either the spec needs updating or the mockup needs trimming.

### 5.8 Two different concepts share the word "Supplier"

- The sidebar entry **"Suppliers"** maps to `ContactsPage` — i.e. the legacy Contact directory (Owners, Villa Managers, Villa Admins, Agents, Management Companies).
- The **Concierge Suppliers** (Settings → Concierge Settings → Suppliers and the per-booking Suppliers tab) are a distinct entity: in-resort vendors (chef, transfers, car hire).
- Spec uses "Contact" for the former (`workflows/05-directory/`). Spec has no model for the latter at all.
- Needs a rename — likely **"Contacts"** for the directory and **"Concierge Suppliers"** for vendors.

### 5.9 Owner-net commission baked into Booking Detail; spec has it on PropertyFinance

- Spec: `01-domain-model.md §PropertyFinance` (referenced from `workflows/03-catalog/property-finance.md`) stores commission %.
- **Mockup:** Booking Detail's Finance section reads `commissionRate = 20` (hardcoded default) and inherits "from property rates" — but the on-the-fly editor on Booking Detail lets you override per booking. Spec doesn't have a per-booking commission override.

### 5.10 Concierge invoiced *with* the villa (Finance tab) vs separately via Payment Lists

- §2.15 Finance tab shows Total = Rental Value + Concierge Value as a single guest invoice — implying concierge is paid alongside the deposit/balance.
- §2.8 Concierge Payment Lists show concierge items billed separately, with their own "Request Payment → Mark Paid" lifecycle.
- These two flows partly overlap. Needs reconciliation: are payment lists for **incremental in-resort spend** layered on top of a pre-stay concierge invoice, or are they the only mechanism?

### 5.11 Soft-deletes vs the CLAUDE.md no-soft-delete rule

- Project rule (`/Users/garethlloyd/projects/villacollective/CLAUDE.md` Principle 5): "No soft delete. No `SoftDeleteModel` / `deleted_at` columns."
- The mockup's `ContactsPage` and `ClientsPage` use a "permanently delete" pattern with confirmation; that's compatible with the rule. **Confirm:** Properties also use a permanently-delete CTA. No conflict — but the AuditLog trail required by the rule isn't surfaced anywhere.

---

## 6. Open questions for product

Before the staff res system can be built, the owner needs to decide on:

1. **Booking Detail layout.** Tabs + right rail (spec) or flat scroll (mockup)? The mockup's flat scroll has a clear visual flow but is hard to navigate; the spec's tabs are easier to deep-link and scope edits. **Recommend: spec.**

2. **Property Detail consolidation.** 13 tabs (mockup, legacy) or the spec's proposed 6 grouped tabs? **Recommend: spec, but seek owner sign-off as it's a real cognitive change for the operations team.**

3. **Availability — multi-villa primary view.** Build the multi-villa timeline (`§3.5`) before the single-villa calendar (`§3.6`), or skip and ship the legacy-style single-villa first? The Quick View Rates modal on Properties hints the multi-villa was prototyped read-only — productise it.

4. **Enquiry list vs kanban.** Ship the list (mockup), the kanban (spec), or both with a toggle? Kanban needs drag-and-drop and stage transitions; list is faster to ship.

5. **Enquiry + Quote in one detail vs separate.** The mockup unifies them. Spec has them as distinct resources. Decision impacts URLs, deep-linking, search, and the data model.

6. **Concierge Level enum (`Quintessential / Signature`).** Is this an additional `Booking.concierge_level` field? Does Signature have a per-booking cost? Does it gate which services are available? How does pricing work?

7. **Discount-split semantics.** Are "commission split" and "VC absorbs full" the only two options, or is there a third "owner absorbs full"? How does this interact with the existing commission rate? Spec'd this once.

8. **Quote sub-statuses.** The mockup adds `Viewed | Follow Up | Deposit Due | Deposit Paid | Cancelled` to the spec's enum. Are these real workflow states or just visual filters? Who/what populates `Viewed` (email-tracking pixel? PDF-view webhook?).

9. **Lead Status & Dead Reason.** Are these per-enquiry fields with a CRM-style scoring model, or just filter chips? Who sets them?

10. **Post-stay feedback.** Whole module is greenfield. Is this in scope for v1 or a future phase? If in scope, decisions needed on:
    - Per-booking aspect template — auto-derived from the live concierge services, or fixed across all stays?
    - Prize draw entry — what's the workflow around it?
    - Public guest-facing form — separate Django app or extend the SPA with a public route?

11. **Regional Manager entity.** Add `RegionAssignment` + thread, or use the existing `ContactPropertyMapping` with a new role? The mockup clearly wants this to be a property-of-region (not property-of-property). What's the relationship to Property? Inferred from `property.region`.

12. **Per-booking team Notes & Comms thread.** Is this distinct from `BookingNote` (`01-domain-model.md §BookingNote` line 235), or just a different presentation? Mockup shows author role pills and timestamps — implies a richer model.

13. **Concierge Payment Lists vs single invoice.** Reconcile §5.10. Likely answer: the Finance tab's "Total Value (rental + concierge)" is the *initial* concierge plan; in-resort additions go on Payment Lists. But this needs confirming.

14. **Quintessential vs Signature feature set.** Settings → Concierge Settings → Concierge Levels has free-text feature bullets. Are these for marketing/display only, or do they actually gate UI? E.g. does Signature hide the Timeline tab?

15. **Custom services per booking.** The mockup lets an EM add a custom service to a single booking. Is that local to the booking or does it create a global service? Mockup's `setCustomServices` is local-only.

16. **Concierge Supplier directory.** Two entry points to the same supplier list (Settings → Concierge Settings and Per-booking Suppliers tab) — does the per-booking edit affect the global list? Mockup syncs them via `window.__vcSuppliers` — needs proper modelling.

17. **Agent: Individual vs Company toggle.** Are these subtypes (single-table inheritance) or one table with a discriminator? Sub-agents have a different model from agents — confirm 1:N.

18. **Quote "Unbranded Links" toggle.** What does this do — strip VC branding from the client-facing quote (HTML email)? Important for trade/agent flows.

19. **Per-user SMTP credentials.** Is this scope creep, or actually needed? If a user leaves, do their pending mail-sends fail? Recommend a single shared MailProvider config instead.

20. **CSV Import.** Is this v1 scope or v1.1? The mapping-preset concept is genuinely useful for migrating off the legacy system, but doesn't need to be polished UI for that.

21. **"Sync to Web" button (per-property + bulk).** What's the trigger model — push immediately, queue, or schedule? Spec has `workflows/11-integrations/public-website-sync.md` but the bulk button needs an explicit answer.

22. **"In Resort" booking status.** Computed or stored? Spec's `Booking.status` enum doesn't include it; mockup tabs treat it as first-class.

23. **`Available (again)` vs `Available` availability statuses.** Same colour, different label — is this a real persisted distinction, or just a label after a cancellation has just freed the dates? If real, it implies an audit trail on availability records.

24. **`Booked` vs `Booked VC` availability statuses.** Both navy. What's the distinction — VC-managed vs externally-managed booking? Implies a `booking.is_external` flag or origin.

25. **Concierge Level required at booking creation.** Booking Detail expects the level to be set; needs to flow from quote → booking or be selected at creation.

26. **Feedback "Prize draw entry" mechanic.** Implies a periodic draw. Out of MVP scope? Stored as boolean only, no draw-run workflow shown.

27. **"Approval required" / `Owner Confirmed` status pill** on Booking Detail header — the second pill (`booking.ownerStatus`) is shown but the spec (`workflows/09-booking/booking-confirmation.md`) treats owner approval as a step, not a persistent status. Reconcile.

28. **Bulk operations.** Spec calls for first-class bulk ops (`05-improvements-over-original.md §13`); the mockup has none except "Sync to Web (bulk)" and the CSV preview select-all. Confirm priority.

29. **Audit log surface.** Spec calls for an audit-log view per record (`§3.8` mentions `History | Audit` tabs on Booking Detail). Mockup has none. Confirm priority.

30. **Feedback workflow — who reads it.** The "Assigned to" field defaults to the EM; the response thread is two-party. Should the regional manager also see/respond? Should the property owner ever see feedback? Mockup doesn't model owner-portal visibility.

---

## Appendix A — Direct references into the bundle (for spot-checking)

If you want to look up something specific in the mockup's JS:

- Navigation array: search for `const _NAV =` (line ~13223 of the served HTML).
- Page-to-component map: `const _NAV_PAGE = {` (line ~13251).
- Property sub-tabs: `const _PROP_TABS = [` (line ~13292).
- Concierge services master list: `const INIT_C_SERVICES = [` (line ~11110).
- Concierge standard items: `const INIT_C_STD_ITEMS = {` (line ~11125).
- Concierge supplier seed list: `const INIT_C_SUPPLIERS = [` (line ~11140).
- Concierge levels: `const INIT_C_LEVELS = [` (line ~11149).
- Booking status tabs: `const BOOKING_STATUS_TABS = [` (line ~3806).
- Payment statuses (Finance page): `const PAYMENT_STATUSES = [` (line ~5767).
- Quote stages palette: `const QUOTE_STAGES = {` (line ~9357).
- Lead statuses + dead reasons: `const LEAD_STATUSES =`, `const DEAD_REASONS =` (line ~9346).
- Booking payment status options (per row): `const PAYMENT_OPTIONS = {` (line ~3149).
- Concierge service-status enum: `const STATUSES = [` (line ~1543).
- Availability status enum: `const STATUS_COLOURS = {` + `STATUS_LABELS` (line ~2428).
- Feedback status flow: `const STATUS_FLOW = ["new", "acknowledged", "responded", "closed"]` (line ~5485).
- Regional Manager assignment seed: `const [regionAssignments, setRegionAssignments] = useState({` (line ~12063).
- CSV import target catalogue: `const VC_SYSTEM_FIELDS = [` (line ~6096).
- Regions per country: `const [regionsByCountry, setRegionsByCountry] = useState({` (line ~12040).
- Feedback seed entries: `window.__vcFeedback = [` (line ~5340).

## Appendix B — Spec doc quick-reference

The most-cited specs and their relevant sections:

- `product-design/01-domain-model.md`
  - §Property (line 54), §PropertyGroup (76), §Collection (79), §Feature (84), §FeatureCategory (89), §POIType (96), §Region & Country (99), §Currency (105), §PriceDisplayConfig (108), §ChangeOverRule (117), §RateCard (133), §RateRule (140), §DiscountRule (156), §Enquiry (165), §Quotation (184), §QuotationLine (191), §Booking (200), §ConciergeLineItem (225), §ArchiveBooking (232), §BookingNote (235), §AvailabilityRecord (254), §Contact (274), §ContactPropertyMapping (283), §Guest (296), §User (303), §DepositPaymentTrack (321), §BalancePaymentTrack (326), §SecurityDeposit (331), §PaymentEvent (342), §CancellationPolicy (369).
- `product-design/02-frontend-design.md`
  - §1.2 Sidebar Groups (line 34), §3.1 Operator Dashboard (146), §3.2 Properties List (179), §3.3 Property Detail Tabs (200), §3.5 Multi-Villa Timeline (274), §3.6 Single Villa Calendar (306), §3.7 Bookings List (322), §3.8 Booking Detail (344), §3.10 Quote Builder (406), §3.11 Enquiry Inbox (437), §3.12 Payments View (462), §3.13 Contact Detail (494), §3.14 Concierge Management (523), §3.15 Reports (541), §3.16 Settings Screens (551), §6.2 Cmd-K palette (683).
- `product-design/04-rest-api-surface.md`
  - §2.2 Properties (106), §2.6 Enquiries (390), §2.7 Quotations (410), §2.8 Bookings (443), §2.9 Concierge Line Items (496), §2.10 Deposit Track (509), §2.11 Balance Track (528), §2.12 Security Deposit Track (546), §2.13 Refunds (563), §2.15 Contacts (590), §2.17 Guests/Clients (624), §2.18 Users (665).
- `product-design/05-improvements-over-original.md`
  - §1 Dashboard (7), §2 Property tabs (13), §3 Booking tabs+rail (19), §6 Multi-villa timeline (37), §7 Quote cart (43), §8 Cmd-K (49), §11 Three payment tracks (70), §13 Bulk ops (86), §14 Concierge with margin (92), §15 Owner portal (98), §16 Audit log (109), §17 Kanban enquiries (115).
- `workflows/06-availability/blocks-and-changeover.md`, `calendar-view.md`, `booking-status-transitions.md`, `holds.md`.
- `workflows/07-enquiry/enquiry-intake.md`, `enquiry-management.md`, `README.md` (open questions).
- `workflows/08-quotation/construction.md`, `lifecycle.md`, `persistence.md`, `transmission.md`, `README.md` (open questions).
- `workflows/09-booking/booking-creation.md`, `booking-management.md`, `booking-modification.md`, `booking-cancellation.md`, `booking-confirmation.md`, `concierge.md`, `payment-schedule.md`.
- `workflows/10-payment/payment-collection.md`, `payment-preauth.md` `[DISABLED]`, `checkout-flow.md`.
- `workflows/05-directory/contact-records.md`, `contact-roles.md`, `contact-property-assignment.md`.
- `workflows/03-catalog/property-master.md`, `property-features.md`, `property-finance.md`, `property-imagery.md`, `property-nearby.md`, `property-rooms.md`.
- `workflows/02-administration/geographic-taxonomy.md`, `financial-taxonomy.md`, `product-taxonomy.md`, `system-configuration.md`.
- `workflows/11-integrations/email-delivery.md`, `public-website-sync.md`, `zoho-crm.md`, `flywire-gateway.md`.
- `workflows/12-automation/scheduler-jobs.md`.
- `workflows/01-identity/user-administration.md`.
