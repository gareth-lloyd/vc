# Owner feedback — Loom transcripts (parsed)

_Source: owner Loom walkthroughs (Contacts/Clients, Availability, Pricing/Seasons,
Quotes/Enquiries). Parsed 2026-07-02. Each item is atomic so it can be triaged /
ticketed independently. Italic notes flag suspected overlap with work already on
local `main`._

## A. Contacts & Clients

- **A1 — Villa-contact categorisation.** Villa contacts need a category/type: owner,
  agent, villa admin, villa manager, management company. Currently all lumped as one
  undifferentiated "Villa Contact".
- **A2 — Introduce "Clients" as a first-class concept.** The people _renting_ the
  villa. Neither the legacy system nor the new one has a clients section (legacy was
  built around enquiries, contact attached to enquiry). Top-level split: **Villa
  Contacts** vs **Clients**.
- **A3 — Address fields on contacts.** Missing today; add full address fields.
- **A4 — Preferred contact method** field (email / phone / etc.).
- **A5 — Tags on contacts/clients** — quick-attach chips: VIP, trade, NIX, friend,
  disability, approach-with-care, etc.
- **A6 — Client profile / 360 view** — connected contacts, previous quotes, previous
  bookings on the client record. _(Overlaps GAP-042 Customer-360 — confirm coverage.)_
- **A7 — Contact interface reused everywhere** — same contact panel replicated across
  the quoting flow and anywhere a contact is relevant.
- **A8 — Agents live inside the Clients list, filterable.** Owner's position (vs Ben's
  separate-section design): an agent _is_ a client with a different category. One list,
  filter by agent vs direct client, plus filters for VIP / repeat / trade + tags.
- **A9 — Companies (B2B) section.** Separate list of B2B companies (e.g. "Done Travel");
  attach an agent contact to a company. _(Overlaps GAP-046 Organisation — confirm this
  matches the B2B-company intent.)_

## B. Availability

- **B1 — Show pricing in the availability search view.** Price by week as the default.
  For sales team talking clients through options live.
- **B2 — Show changeover day** in the availability view.
- **B3 — Show the month above the date range** in the availability grid (readability
  for sales team).
- **B4 — Click-and-drag to add availability.** Current date-range entry is clunky; needs
  to be fast for busy periods.
- **B5 — "Last updated" + a confirm/refresh button.** Last-updated resets whenever
  availability changes; also a button to reset last-updated _without_ adding dates
  (confirm "still correct"). _(Overlaps GAP-033 Availability freshness — confirm the
  confirm-button UX exists.)_
- **B6 — Owner calendar link field.** For villas with an online calendar but no iCal: a
  link the salesperson can open to check the owner's live calendar. Where iCal exists,
  label it "iCal" so they know it's the latest owner feed.

## C. Pricing & Seasons

- **C1 — Regional dropdown on the properties/bookings list** (already has all-countries +
  all-status; add region).
- **C2 — Split "Seasons" into Services vs Pricing.** "Services" = inclusions (date range
  + copy), its own tab; rates/pricing separate.
- **C3 — Price-per-week bands.** Rethink rates for the new season model — price bands for
  different pricing, priced per week.
- **C4 — Group weeks into named seasons.** Bunch dates/weeks together and name them (top
  peak, high season, shoulder). Seasons as named groupings over the pricing calendar.
- **C5 — Gross ⇄ Net with commission auto-calc.** Enter either net (add e.g. 20%
  commission → auto gross) or gross (take commission off). Both directions,
  auto-calculated. _(Related to BUG-009 price-basis engine — but this is the data-entry
  convenience layer.)_
- **C6 — Nightly pricing.** For odd-length bookings (10–15 days) outside week blocks.
  Flagged as complex — decimals/rounding need care. Needs a more flexible pricing model.

## D. Quotes & Enquiries

- **D1 — Enquiry → multiple stacked quotes.** Flow: lead → qualified → enquiry → quote.
  Must stack many quotes under one enquiry, to track quotes-per-conversion. Not how it
  works today.
- **D2 — Richer enquiry list/dashboard.** Too light now. Add columns: name, region,
  enquiry, quote, date, salesperson (assignable), date range, etc.
- **D3 — Richer new-enquiry form.** Add address (hideable but useful for repeat bookers),
  customer notes, tags (trade, NIX, friend, approach-with-care, disability, VIP).
- **D4 — Full customer profile on the enquiry.** Enquiry history (enquiries, quotes,
  calls), linked contacts (spouse, child, PA), previous bookings — a full profile for the
  sales team at quote time. _(Overlaps GAP-042.)_
- **D5 — Date-range quoting, not fixed dates.** Quote search must take a date range and
  let the salesperson click all the weeks they want to quote. Fixed price/fixed date is
  wrong. _(Overlaps GAP-043 multi-week builder — confirm.)_
- **D6 — Occupancy-based pricing lines in the quote builder.** Per week box, separate
  lines per occupancy band (8–10 = 120, 10–12 = 140, 12–14 = 160), checkboxes checked by
  default so the client sees all band prices. _(Overlaps GAP-044 occupancy fan-out — likely
  already done; confirm it matches this UX.)_

---

_23 items across four areas. Completeness assessment against current `main` appended
below._

---

# Completeness assessment (vs current `main`)

_Assessed 2026-07-03 via parallel codebase sweep (backend + frontend + design specs).
Guide-assumption held up: **19 of 23 DONE end-to-end, 4 PARTIAL, 0 untouched.** The
recent GAP-0xx work covers the overwhelming majority of this feedback directly._

## Scoreboard

| # | Item | Status |
|---|------|--------|
| A1 | Villa-contact categorisation (owner/agent/admin/manager/mgmt-co) | ✅ DONE |
| A2 | "Clients" as first-class concept (PersonKind CUSTOMER vs CONTACT) | ✅ DONE |
| A3 | Address fields on contacts | ✅ DONE |
| A4 | Preferred contact method | ✅ DONE |
| A5 | Tags (VIP/trade/NIX/friend/disability/approach-with-care…) | ✅ DONE |
| A6 | Client 360 (connected contacts, quotes, bookings) | ✅ DONE |
| A7 | Contact panel reused across enquiry/quote | ✅ DONE |
| A8 | Agents in Clients list, filterable (agent-vs-direct + tag filters) | ⚠️ PARTIAL |
| A9 | Companies (B2B) section | ✅ DONE |
| B1 | Pricing in availability search view (price/wk) | ✅ DONE |
| B2 | Changeover day shown | ✅ DONE |
| B3 | Month label above date range | ✅ DONE |
| B4 | Click-and-drag to add availability | ✅ DONE |
| B5 | Last-updated + confirm button (no date add) | ✅ DONE |
| B6 | Owner calendar link field (iCal-labelled) | ✅ DONE |
| C1 | Regional dropdown on properties list | ✅ DONE |
| C2 | Split Services vs Pricing | ✅ DONE |
| C3 | Price-per-week bands | ✅ DONE |
| C4 | Group weeks into **named season tiers** (peak/high/shoulder) | ⚠️ PARTIAL |
| C5 | Gross ⇄ Net with commission auto-calc | ✅ DONE |
| C6 | Nightly pricing (odd-length bookings) | ✅ DONE |
| D1 | Enquiry → many stacked quotes | ✅ DONE |
| D2 | Richer enquiry list/dashboard | ✅ DONE |
| D3 | Richer **new-enquiry form** (address/notes/tags at creation) | ⚠️ PARTIAL |
| D4 | Full customer profile on enquiry (incl. **calls**) | ⚠️ PARTIAL |
| D5 | Date-range quoting, multi-week select | ✅ DONE |
| D6 | Occupancy-band lines, default-checked | ✅ DONE |

## The four PARTIALs (all the real gaps)

### C4 — Named season tiers (peak / high / shoulder) — **biggest structural gap**
A `RatePeriod` is a named date span, but its `name` is free text with **no tier
classification**. The owner explicitly asked to "categorize certain sections of the
pricing calendar as high season, peak, shoulder." There is no `tier` / `season_type`
field on `RatePeriod`; the concept is deferred to **Q-022**. This is the one item that
needs a model change (enum field + migration + workbench UI + optional colour-coding),
not just wiring.
- Evidence: `django_res/pricing/models/rate.py:62-106` (docstring says grouping-by-tier
  is "a separate concern (Q-022)").

### D4 — Calls (and rich notes) missing from the customer profile
The customer-360 panel shows enquiries, quote counts, bookings, linked contacts
(spouse/child/PA — all present). But there is **no call log** fetched or rendered
anywhere, and rich notes aren't in the panel. The owner listed "inquiries, the quotes,
of calls" as the enquiry history. Calls were deferred in GAP-042 and remain unbuilt —
there is no call model/timeline at all. Needs a call-log concept if we want it.
- Evidence: `CustomerProfilePanel.tsx:41-63` (no calls hook/component).

### A8 — Contacts-list filters are backend-only
Backend already supports the agent-capacity predicate (`agency` or active agent role)
and `?tags=vip,trade` overlap filtering, but the contacts list UI exposes **only
kind + status** selects. No "agent vs direct client" facet, no VIP/repeat/trade/tag
filter controls. **FE-only work** — the data layer is ready.
- Evidence: `contact.py:110-120` (predicate exists) vs `ContactsListPage.tsx:70-206`
  (only two selects rendered).

### D3 — Richer new-enquiry *form* not built
Address (hideable), customer notes, and tags all exist on the `Person` record and are
editable on the contact profile — but they are **not surfaced on the enquiry-creation
form**. You reach them only indirectly via the ContactPicker. **FE-only** (decide which
fields belong at enquiry-creation time vs the linked contact).
- Evidence: `EnquiryFormDialog.tsx:245-489` (no tags/address/notes fields).

## Minor notes (not gaps, worth a glance)
- **D1** — no distinct "qualified" pre-enquiry stage; lead→qualified→enquiry is collapsed
  (everything is an Enquiry from creation; "lead quality" is the orthogonal LeadStatus
  temperature). If Zoho hands off already-qualified leads this is fine; flag only if a
  pre-enquiry stage is wanted.
- **D2** — enquiry list has no quote-count / latest-quote column (quote data only on the
  detail page). The owner's mock listed "enquiry" and "quote" as distinct columns.
- **B3** — month label sits in the toolbar header, not banded directly over the day
  columns. Readability requirement met; cosmetic only.

## Bottom line
The recent work landed almost all of this. Only **C4 (season tiers)** is a genuine
model-level gap; **D4 (calls)** is a missing feature area; **A8** and **D3** are
FE-surfacing of data that already exists. Everything else is shipped.
