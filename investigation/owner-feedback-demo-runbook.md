# Demo runbook — owner feedback fixes

_Click-through sequences to demonstrate each addressed point. Ordered to flow naturally
with minimal back-and-forth. Routes are real; use a property/contact/enquiry that has
seeded data (run `seed_dev` with realistic pricing first)._

**Suggested order:** Contacts → Availability → Pricing → Quotes/Enquiries.
🟡 = partly done; the runbook notes what to say.

---

## 1. Contacts & Clients

### Villa-contact roles (feedback #1)
- Go to a property → **People** tab (`/properties/:id/people`)
- Point out each contact's **role badge** (owner, villa manager, agent, management company…)
- Click **Add** → show the role picker in the assignment dialog

### Clients as their own record + tags + address + preferred method (#2, #3, #4, #5)
- Go to **Clients** (`/clients`)
- Point out this is a dedicated list, separate from villa-side contacts
- Show the **one-click tag chips** on a row (VIP / Trade / etc.)
- Open a client → **Details** tab
  - Point out the **address block** (lines, town, postcode, country picker)
  - Point out **preferred contact method** (email/phone/SMS)
  - Show the **tag editor** — attach/detach a tag inline (VIP, disability, approach-with-care…)

### Client 360 profile (#6) + reused everywhere (#7)
- Still on the client Details tab, point out the **customer profile panel**: linked
  contacts, enquiry history (with quote counts), previous bookings
- Then open an **enquiry** (`/enquiries/:id`) and a **quote** (`/enquiries/quotes/:id`)
- Point out the **same profile panel** appears on both — "one interface, everywhere"

### Companies / B2B (#9)
- Go to **Companies** (`/companies`) → open one (e.g. an agency)
- Show company details; then on a contact form, show the **company picker** attaching a
  contact to that company

### 🟡 Agent / tag filters on the list (#8)
- On **Contacts/Clients**, show the current **kind** and **status** filters working
- _Say:_ "agents and clients already share one directory and the filtering exists under
  the hood — the agent-vs-direct and VIP/tag filter controls are the next small UI add."

---

## 2. Availability

### Sales search view — pricing, changeover, month label (#10, #11, #12)
- Go to **Availability** (`/availability`)
- Filter by region / bedrooms to get a shortlist
- Point out, per villa:
  - the **"from £X / week"** headline next to the name
  - the **per-week price strip** under each villa
  - the **changeover day** (icon + weekday, diagonal marker on the week)
- Point out the **month label** ("June 2026" / spanning range) above the grid
- Point out the **iCal badge** / **online-calendar link** on each row (feedback #15)

### Add availability by drag + confirm freshness (#13, #14)
- Open a property → **Availability** tab (`/properties/:id/availability`)
- **Drag-select** a date range across the calendar → show the block dialog pre-filled → save
- Point out the **freshness panel**: owner-updated / calendar-imported / VC-confirmed dates
- Click **"Confirm still correct"** → point out the confirmed date updates **without**
  adding any new block
- Point out the **iCal badge or owner-calendar link** here too (#15)

---

## 3. Pricing & Seasons

### Region filter on properties (#16)
- Go to **Properties** (`/properties`)
- Show the **region** dropdown filtering alongside country and status



### Weekly bands + net/gross auto-calc + nightly (#18, #20, #21)
- On the **Rate Workbench** (`/properties/:id/rate-workbench`)
- Show the **occupancy matrix** with **weekly** prices editable inline (#18)
- Open a **rate band** editor → type a price and point out the live **"owner net" /
  "guest price"** counterpart that recalculates (#20) — flip the plan's basis (net ↔ gross)
  to show it works both ways
- Point out (or demo via the live probe) a **non-week stay length** (e.g. 10 nights)
  pricing night-by-night (#21)

### 🟡 Named season tiers (#19)
- On the workbench timeline, show you can **create a named period** over a span of weeks
- _Say:_ "naming and pricing a span works today; the next step is tagging a period as
  **peak / high / shoulder** as a proper tier for colour-coding and reporting — a small
  model addition still to come."

### Create a property from the UI
- Go to **Properties** (`/properties`) → **Create property** button → fill the dialog → save
- Point out this didn't exist before — properties previously only arrived via migration

### Rate Workbench — power features beyond the basics
- On the **Rate Workbench** (`/properties/:id/rate-workbench`):
  - Flip the **pricing-mode toggle** — flat vs occupancy-based pricing per plan
  - Point out **historical rate periods are hidden and locked read-only** (past pricing can't
    be edited by accident)
  - Point out the **coverage-gap lane** flagging uncovered dates, and the stacked
    **nightly + weekly** inline editors in the matrix
---

## 4. Quotes & Enquiries

### Richer enquiry list + Kanban (#23)
- Go to **Enquiries** (`/enquiries`)
- Toggle **List ↔ Kanban**
- Point out the columns: guest, property, region, dates, party, **salesperson**, source,
  status, lead temperature
- Open the **assign** action → assign a salesperson

### Stacked quotes under one enquiry (#22)
- Open an enquiry (`/enquiries/:id`)
- Point out the **quote stack** — multiple quotes under the one enquiry
- Point out the **quotes-to-convert count**
- Click **"Build another quote"** to show a new quote stacks onto the same enquiry

### Date-range, multi-week quoting (#26)
- In the quote builder (from the enquiry, or `/quotations/new`)
- Point out the search takes an **arrival window** (arrive-from / arrive-to), not a fixed date
- In a result, use the **week strip** to **tick several weeks** → each becomes its own line

### Occupancy-band lines (#27)
- In the same result, point out each week shows a **line per occupancy band**
  (e.g. 8–10, 10–12, 12–14) with prices
- Point out they're **ticked by default** — "the client sees every option; untick to trim"

### 🟡 New-enquiry form fields (#24)
- Open **New enquiry** → show the core fields captured
- _Say:_ "address, notes and tags all exist on the linked contact record; surfacing them
  on this creation form is a quick front-end follow-up."

---

## 5. Beyond the feedback — extra progress worth showing

_Complete, demo-able work that wasn't raised in the Looms. Lead the "extras" with damage
claims and 2FA — they're whole features nobody asked for._

### Damage claims (security-deposit workflow)
- Go to **Bookings** (`/bookings`) → open a booking with a security deposit (`/bookings/:id`)
- Find the **Damage Claims** section → **Add a claim** (amount + description)
- Walk the state machine: **Approve** the claim (OPEN → APPROVED)
- Open the **Photos** dialog → upload an evidence photo
- Point out settlement is **auto-set when the security deposit is captured** (via the
  Capture-for-damages action) — there's no manual "settle" step, it's driven by the money movement

### Staff 2FA + refund step-up
- Log in as a staff user who hasn't enrolled → you're routed to **`/enroll-2fa`** (forced enrolment)
- Complete enrolment (authenticator app), then show the **`/login/2fa`** challenge on next sign-in
- On a booking with a captured payment, start a **refund** → point out the **TOTP step-up
  dialog** gates execution (a fresh code required for the sensitive action)



### Bookings list filters
- On **Bookings** (`/bookings`), show the **date-range filter** and the
  **"exclude terminal"** toggle (hide cancelled/completed) narrowing the list

### DateRangePicker (consistency win)
- Not a standalone screen — call it out opportunistically as you use date ranges anywhere
  (availability block, quote window, rate period, modify-dates): "the **same** single-trigger
  range picker everywhere now, with nights/days modes" — replaced a dozen inconsistent inputs
  


---

## Quick "what to emphasise" cheat-sheet
- **Fully done and worth dwelling on:** availability search pricing + drag-add + freshness
  confirm; the reused customer 360 panel; net↔gross auto-calc; occupancy-band quote lines;
  stacked quotes per enquiry.
- **Be upfront about the four in-progress items:** season tiers (#19), calls (#25), list
  filters (#8), enquiry-form fields (#24) — three are small front-end finishes; only season
  tiers needs new groundwork.
