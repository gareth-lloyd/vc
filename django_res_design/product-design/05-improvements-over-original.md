# 05 — Improvements Over the Original

This document catalogs every place the redesign deliberately diverges from the .NET / Blazor system, with the rationale. Use it during stakeholder review to confirm each change is desired before implementation.

The brief was: *reproduce familiar functionality and flow without slavish devotion to the original design*. Everything below is an intentional improvement, not an accident of rewrite.

## 1. Dashboard becomes useful

**Was**: A paginated property list. Operators ignored it and worked from bookmarks.
**Now**: Operator dashboard with KPIs (check-ins / check-outs today, open enquiries, overdue payments, quotes awaiting reply) and actionable lists (today's arrivals/departures, recent enquiries, recent quote activity). Each KPI links into a filtered deep view.
**Why**: A dashboard should answer "what do I need to act on right now?" — the original answered "what properties exist?" which the Properties page already does.

## 2. Property detail collapses 14 tabs into 6

**Was**: Overview / Rates / Finance / Availability / Rooms / Features / Nearby / Contacts / Extras / Settings / Images / Descriptions / Import Rooms / Importers — 14 tabs.
**Now**: Details / Pricing / Availability / People / Media / Settings — 6 tabs. The original Rooms, Features, Nearby, and Descriptions fold into Details. Finance, Rates, Extras fold into Pricing. Contacts becomes People. Images becomes Media. Importers move into Settings, and "Import rooms" becomes a button inside Details → Rooms.
**Why**: 14 tabs forces operators to remember which tab holds which field. The grouping by concern means an operator looking for "anything about price" goes to Pricing, anything about "who can see/edit this" goes to People.

## 3. Booking detail: monolithic scroll → tabs + right rail

**Was**: One page with 11 collapsible cards stacked vertically (status / customer / payer / agent / notes / booking details / owner / villa info / finance / concierge / actions). A ~3000-pixel scroll.
**Now**: Six tabs (Overview / Finance / Payments / Concierge / Owner / Timeline) + a persistent right rail showing the booking summary and next-action.
**Why**: Operators repeatedly lose context scrolling between sections. The right rail anchors "what is this booking" while they work in any tab.

## 4. Status: colour-only → icon + colour + label

**Was**: Status badges were coloured chips. Operators learned colour-to-status mapping but new hires struggled; colour-blind users were excluded.
**Now**: `<StatusBadge>` always renders icon + colour + text. Lifecycle progress for bookings is shown as a 5-pip indicator with hover-tooltips and a `!` overlay for overdue.
**Why**: WCAG. Onboarding. Honest communication of state.

## 5. Contact-property permission matrix → role presets with override

**Was**: 12 boolean flags per contact-property mapping (`IsAccessInfo`, `IsAccessAvail`, `IsAccessRates`, `IsAccessBooking`, `IsAccessConfirmAuth`, `IsAccessSlip`, `IsNotifyInfo`, `IsNotifyAvail`, `IsNotifyRates`, `IsNotifyBooking`, `IsNotifyConfirmReq`, `IsNotifySlip`, plus `IsPrimaryContact`, `IsCC`). An unreadable wall of checkboxes per mapping.
**Now**: Role preset dropdown (Owner / Manager / Agent / Concierge / Accountant / Read-only / Viewer) on each mapping, with a `⚙ Customize` toggle that exposes the raw 12 flags only when a true exception is needed. Customised role displays as "Owner (custom)" to flag the divergence.
**Why**: 12 booleans is data, not UX. 95% of mappings fall into one of five presets; the 5% that don't can still customise.

## 6. Calendar: single-villa only → multi-villa timeline as primary

**Was**: A single-villa month-grid calendar. To see the whole region you opened each villa in turn.
**Now (shipped)**: A Gantt-style multi-villa timeline (`/availability`). Rows are villas, X-axis is dates, coloured bands are bookings/holds. Filter-first: nothing renders (and nothing is fetched) until at least one filter is set — the portfolio is too large for show-all. Click a band for a summary popover that deep-links to the booking detail or the villa calendar; the timeline itself is read-only (drag-to-modify was dropped — date/villa changes carry pricing implications that belong on the booking detail). The single-villa month-grid is still available (`/properties/:id/availability`) for the cases where it's the right view.
**Why**: Ops people work at portfolio level — "what's happening across all my villas next week" is the high-frequency question.

## 7. Quote building → first-class multi-villa cart

**Was**: Quote-building UI was buried under "Quotes & Enquiries → New Quote" and worked one villa at a time, with no clear cart-vs-search separation.
**Now**: A two-pane builder: left pane is the enquiry brief + villa search/filter; right pane is the cart of selected villas with per-line price overrides. Each result card shows live availability + computed price for the requested dates. Preview email before send. Optional 48h auto-hold on quoted villas at send time.
**Why**: This matches what operators actually do — assemble a few options for a guest, override prices where needed, send one consolidated quote.

## 8. Global search (Cmd-K palette) — entirely new

**Was**: No global search.
**Now**: Cmd-K palette anywhere. Type `VC2391` to jump to a booking, `QVC184` to a quote, a guest email to their contact, a villa name to its detail. Scoped prefixes (`b:`, `e:`, `p:`, `c:`, `>`). Action verbs ("New booking", "Send reminder for ..."). Recent items on empty input.
**Why**: For ops users who handle dozens of entities per hour, a keyboard-first jump is the single highest leverage UX investment.

## 9. Email send → always preview-before-send

**Was**: Many points fire emails silently (acknowledgement, confirmation, owner notification, payment requests).
**Now**: Every outbound email step surfaces a preview modal with editable subject + intro + sign-off, then awaited send. Auto-reminders are queued but optionally human-reviewable (per-site flag).
**Why**: Operators repeatedly burned by silent sends with wrong template variables or stale data. Cost of preview is one click; cost of bad email to a guest is real.

## 10. Booking modification: explicit editability rules + concurrency

**Was**: Modifications locked entirely after the first payment was received. No diff. No concurrency handling — last save wins.
**Now**:
- An explicit editability table by booking state (`Underway` / `DepositPaid` / `Confirmed` / `Completed` / `Cancelled`), surfaced in UI as greyed fields with tooltips ("Locked because deposit paid — Senior Op required").
- Concurrent edits detected via `etag` / `updated_at`; 409 returns a diff modal ("Sara changed the deposit 3 minutes ago — keep yours / keep theirs / merge field-by-field").
- A booking timeline tab shows every change with before/after diff and the actor.
**Why**: The original "lock after first payment" was a blunt instrument. Real life has date changes, party-size changes, price overrides post-payment, and they need to be possible — just controlled and audited.

## 11. Three payment tracks modelled explicitly

**Was**: One Payments region on the booking, with a status enum that varied across deposit / balance / SD in fuzzy ways. Hard to reason about "what state is the security deposit in".
**Now**: Three explicit resources — Deposit, Balance, Security Deposit — each with its own state machine, its own action endpoints (`request-payment`, `mark-paid`, etc.), and its own UI card on the Payments tab. Security adds `hold` / `release` / `claim` for pre-auth. Each track shows its own milestones, due date, and next action.
**Why**: Conceptually they're three independent money flows. Modelling them as one was the source of frequent operator confusion.

## 12. Refunds: online + offline parity, partial stacking, fallback

**Was**: Refunds were booking-level, online only, single-shot.
**Now**:
- One refund flow handles online (Flywire API) and offline (BT-issued, mark with reference).
- Partial refunds stack against a single payment, each tracked as its own RefundEvent.
- Refund-window-exceeded (Flywire's gateway-side window, typically 90-180 days depending on payment method) automatically routes to the BT-offline path with operator confirmation.
- Per-payment-stream refunds (deposit, balance, SD, concierge each refunded independently with their own amount/method).
**Why**: Real refund flows are messy. The original silently failed on edge cases; this models the cases.

## 13. Bulk operations as first-class UI

**Was**: Anything cross-property was a request to the database team or ad-hoc SQL.
**Now**: A 3-step wizard (Pick scope → Configure change → Preview & confirm) for: block dates across many villas, bulk rate change with % or fixed delta, bulk feature toggle, bulk policy update, inventory export. Preview shows villa-by-villa before/after with conflicts flagged. Partial completion is allowed; final summary shows X succeeded, Y skipped with reasons.
**Why**: Ops users now do this themselves; database team is freed.

## 14. Concierge: per-line state, supplier cost, margin tracking

**Was**: Concierge had a single booking-level state and a free-text description for each item. Supplier costs and margins lived in operator spreadsheets.
**Now**: Each line is a first-class entity with its own state machine (`Awaiting` / `Sent` / `Paid` / `Failed` / `Included`), currency, supplier link, supplier cost (internal-only), and payment timing. Batch-charge across multiple lines into one payment link. Margin reports roll up per supplier and per villa.
**Why**: Concierge is becoming a meaningful revenue stream; treating it as a string was leaving money on the table.

## 15. Owner portal upgrades

**Was**: A separate "Owner Area" with limited views and no notification controls.
**Now**:
- Per-property notification settings (an owner with 4 villas can be loud on one, quiet on three).
- PDF + CSV statements (accountants love CSV).
- Owner-initiated block requests with operator approval flow (was "email the ops team").
- Redacted-by-default guest info (initials only) with per-permission unhide. GDPR-friendly.
- Magic-link login option for low-volume owners (no password to forget).
**Why**: Owners are the long-term retention factor. The original portal felt vestigial.

## 16. Audit log and concurrency etags everywhere

**Was**: No structured audit log. `UpdatedAt` / `UpdatedBy` on each row was the only trace; no field-level diff.
**Now**: A central `AuditLog` records every state transition, edit, email send, and money movement, with actor + before/after JSON + correlation ID. Every editable resource has an etag; PATCH/PUT requires the etag, returns 409 on stale.
**Why**: Required for the modification flows (#10) and for any compliance review. Should have been there from day one.

## 17. Enquiry pipeline as kanban

**Was**: Enquiries were a flat list with a status field. Operators tracked their pipeline in their head.
**Now**: Kanban with status columns (New / Qualifying / Quote-sent / Won / Lost) is the default; drag a card to advance status. List view is still available for power users who want sortable columns.
**Why**: Enquiries are inherently a pipeline. Treating them as a list misrepresents the work.

## 18. Hold semantics made explicit

**Was**: "Holds" existed but their expiry, who set them, and how to extend was opaque. They sometimes auto-released, sometimes not.
**Now**: A hold has a visible expiry countdown in the UI, a server-side scheduled job releases expired holds with a log entry, operators can `extend-hold` or `release-hold` via dedicated actions, and quotes can optionally auto-place holds on quoted villas at send time.
**Why**: Holds were a source of double-bookings and operator anxiety.

## 19. Reports unified into a single hub

**Was**: Several disparate report screens, each with its own UX.
**Now**: One Reports hub with tiles per report type (Owner statements / Occupancy / Revenue & commission / Concierge margin / Refunds & cancellations / Enquiry funnel / Operator productivity). Common controls (period, scope, grouping, filters). Preview inline before export. Schedule recurring reports with email recipients.
**Why**: Consistency reduces training cost and surface area for bugs.

## 20. Operator-visible communications history + editable email-template admin

**Was**: Outbound mail is dumped to per-day plaintext files under `wwwroot/ResLogs/<ddMMyyyy>/` via `Utilities.WriteResLogFile`. There is no per-booking communications history, no queryable log, no "what was sent" view. Templates live in the `VCEmailTemplates` SQL Server table and are editable only via direct SQL — no UI, no versioning, no preview, no test-send. (`mock_up_analysis/04a-ressystem-email-inventory.md §2.4, §3.1, §8`.)
**Now**:
- `EmailLog` (already in v1 — see `10-comms.md`) is a first-class, queryable, append-only record of every dispatch attempt, correlated to `booking_id` / `quotation_id` / `enquiry_id` / `payment_id`.
- A **Comms tab** on Booking Detail (`02-frontend-design.md §3.8`) lists every email sent against the booking, with view-payload, resend, and a compose-new action backed by the template catalogue.
- `EmailTemplate` is first-class and admin-editable, with **versioning** (active row swap on publish), **preview-with-data** (render against a real or synthetic context), **test-send** (writes a `correlation.test_send=True` `EmailLog` row), and full audit trail. Endpoint surface: `04-rest-api-surface.md §2.19`.
**Why**: Legacy operators had zero forensic visibility into outbound mail and zero ability to fix template copy without a database engineer. Both are foundational improvements; together they retire the legacy "SQL-only templates + plaintext ResLogs" model entirely. Cross-refs: `10-decisions.md` (the two live decisions "Per-booking Communications tab on Booking Detail" and "Editable `EmailTemplate` admin with versioning + preview-with-data + test-send"), `10-comms.md` (template catalogue + admin UX), `mock_up_analysis/04a-ressystem-email-inventory.md §10` (legacy gap analysis).

## 21. Greenfield model collapses legacy redundancy

The legacy schema accreted parallel tables that overlapped in purpose. The new model:
- Collapses `VillaWebsitePricing` and `VillaMapping` (price display) into one `PriceDisplayConfig` resource.
- Splits the embedded property-level settings out of `VillaMaster` into `PropertySettings` and `PropertyFinance` resources for cleaner update semantics.
- Renames `VillaConfigPropertyDefault` to `SystemDefaults`, exposed in admin only.
- Drops `VillaContactMap` (overlaps `VillaContactMapping`).
- Drops `VillaContactRoleMapping` (rolled into mapping role preset).
- Renames domain-language entities (`VillaEnquire` → `Enquiry`, `VillaBooking` → `Booking`, `VillaClientDetail` → `Guest`).

## What we are NOT changing

For clarity, things we are deliberately keeping familiar:
- **The Enquiry → Quotation → Booking funnel.** Operators know this; it works.
- **Three payment tracks per booking** (deposit / balance / security). The model is correct.
- **Concierge tier semantics** (Quintessential vs Signature). Carried over.
- **Multi-site / multi-currency / multi-country**. Carried over.
- **Status names on availability** (Available / Hold / Booked / Unavailable / Available-Enquire) — same vocabulary, with half-day variants.
- **Owner-permission concept** — same idea, simpler UI (improvement #5).
- **Zoho integration as the CRM of record**.
- **OTA channel sync** (Airbnb / Booking.com / VRBO) as a future-state requirement.

When in doubt during implementation: improvements above are deliberate, everything else mirrors the original.
