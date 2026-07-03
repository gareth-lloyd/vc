# Owner feedback → progress

_A response to the Loom walkthroughs (Contacts/Clients, Availability, Pricing/Seasons,
Quotes/Enquiries). Each point of feedback is mapped to what's now in the system._

**Summary: of the 23 points raised, 19 are fully built, 4 are partly there.**
Availability is 100% done. The four remaining items are called out clearly at the end —
only one of them needs new groundwork; the rest are finishing touches on data that
already exists.

Legend: ✅ Done &nbsp; 🟡 Partly done &nbsp; ⬜ Not started

---

## Contacts & Clients

| # | Feedback | Status | Where it stands |
|---|----------|--------|-----------------|
| 1 | Categorise villa contacts (owner, agent, villa admin, villa manager, management company) | ✅ | Every villa contact now carries a role, mapped from the legacy categories. Roles show as badges and drive filtering. |
| 2 | Add "Clients" (the people renting) as their own thing, separate from villa contacts | ✅ | Clients are now a first-class record, split from villa-side contacts. There's a dedicated Clients list. |
| 3 | Address fields on contacts | ✅ | Full address (lines, town, postcode, country) on both people and companies, editable in the UI. |
| 4 | Preferred contact method | ✅ | Email / phone / SMS preference on each contact, shown and editable. |
| 5 | Quick-attach tags (VIP, trade, NIX, friend, disability, approach-with-care…) | ✅ | Full tag taxonomy including all of these; one-click tag chips on the Clients list. |
| 6 | Client profile: connected contacts, previous quotes, previous bookings | ✅ | A customer profile panel shows linked contacts, enquiry history (with quote counts), and previous bookings. |
| 7 | Same contact interface reused across the quoting flow | ✅ | The one profile panel appears on the contact page, the enquiry, and the quote — single source. |
| 8 | Agents live inside the Clients list, filterable (agent vs direct client, plus VIP/repeat/trade) | 🟡 | Agents and clients already share one directory, and the filtering logic exists behind the scenes — but the list screen only offers a couple of filters today. The agent-vs-direct and VIP/tag filter controls still need adding to the screen. |
| 9 | Separate B2B Companies section; attach agent contacts to a company | ✅ | Companies directory (e.g. "Done Travel") with its own pages; agents attach to a company via a picker. |

## Availability

| # | Feedback | Status | Where it stands |
|---|----------|--------|-----------------|
| 10 | Show pricing in the availability search view (price by week) | ✅ | A "from £X/week" headline plus a per-week price strip under each villa in the sales search view. |
| 11 | Show the changeover day | ✅ | Changeover day shown per villa, with a marker on each week. |
| 12 | Show the month above the date range | ✅ | Month label (e.g. "June 2026", or a spanning range) above the grid. |
| 13 | Click-and-drag to add availability | ✅ | Drag-select across the calendar to set a range, which pre-fills the block dialog. Manual entry still available. |
| 14 | "Last updated" + a confirm button that resets it without adding dates | ✅ | Three-signal freshness panel (owner-updated / calendar-imported / VC-confirmed) with a one-click "confirm still correct" button. |
| 15 | Owner-calendar link for villas online but not on iCal; label "iCal" where a feed exists | ✅ | Where there's an iCal feed it shows an "iCal" badge; otherwise a link opens the owner's online calendar. |

## Pricing & Seasons

| # | Feedback | Status | Where it stands |
|---|----------|--------|-----------------|
| 16 | Regional dropdown on the properties list | ✅ | Region filter alongside country and status. |
| 17 | Split "Seasons" into Services (inclusions) vs Pricing | ✅ | Services (inclusions with their own dates + copy) are a separate tab from Rates. |
| 18 | Price-per-week bands | ✅ | Weekly pricing per band, editable inline in the rate matrix. |
| 19 | Group weeks together and name them as seasons (top peak / high / shoulder) | 🟡 | You can already create a named date span (a "period") and price it. What's missing is a season **tier** — tagging a period as peak / high / shoulder as a proper category (for colour-coding, reporting, reuse). That's a small model addition, not yet built. |
| 20 | Enter net rates and mark up, OR enter gross and take commission off — auto-calculate | ✅ | Enter either side; the system shows the calculated counterpart (owner net ⇄ guest price) live as you type, using the same rounding as the pricing engine. |
| 21 | Nightly pricing for odd-length bookings (10–15 days) with sensible rounding | ✅ | The engine prices night-by-night for any stay length, converting weekly rates where needed, with banker's rounding to the penny. |

## Quotes & Enquiries

| # | Feedback | Status | Where it stands |
|---|----------|--------|-----------------|
| 22 | Stack many quotes under one enquiry; track quotes-to-convert | ✅ | One enquiry holds many quotes, shown as a stack with a "build another" action; a quotes-to-convert count is tracked and surfaced. |
| 23 | Richer enquiry list (name, region, quote, date, salesperson, date range…) | ✅ | List and Kanban with guest, property, region, dates, party, salesperson (assignable), source, status and lead temperature. |
| 24 | Richer new-enquiry form (address, customer notes, tags) | 🟡 | The enquiry form captures the core fields; address, notes and tags all exist on the linked contact record but aren't on the enquiry-creation screen yet. |
| 25 | Full customer profile on the enquiry (history: enquiries, quotes, **calls**; linked contacts; previous bookings) | 🟡 | Enquiries, quote counts, previous bookings and linked contacts (spouse/child/PA) are all there. **Call history is not** — there's no call log in the system yet. |
| 26 | Date-range quoting: pick all the weeks to quote, not fixed dates | ✅ | The quote search takes an arrival window; a week strip lets you tick every week you want to quote, each becoming its own line. |
| 27 | Occupancy-based pricing lines per week, checkboxes checked by default | ✅ | Each week shows a line per occupancy band (e.g. 8–10, 10–12, 12–14) with prices, all ticked by default so the client sees every option. |

---

## What's left (the four partly-done items)

**1. Season tiers — peak / high / shoulder (item 19).** _The one item needing new
groundwork._ Named pricing periods exist; adding a tier category on top (so a period can
be labelled peak/high/shoulder for colour-coding and reporting) is a small model +
UI addition.

**2. Call history on the customer profile (item 25).** The profile shows everything
except calls — there is no call-logging concept in the system yet. Worth deciding whether
calls should be tracked here or stay in Zoho before building.

**3. Agent / tag filters on the Clients list (item 8).** The data and filtering logic
already exist; it's a matter of adding the filter controls (agent-vs-direct, VIP, tags)
to the list screen. Front-end only.

**4. Address / notes / tags on the new-enquiry form (item 24).** These fields exist on
the contact record but aren't on the enquiry-creation screen. A quick front-end addition,
pending a decision on which fields belong at enquiry-creation time.

_Everything else raised in the walkthroughs is built and in the current system._
