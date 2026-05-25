# Owner Portal — Mockup Analysis

> **STATUS: DEPRIORITISED (beyond the read-only v1 spec).** The legacy `ResSystem/` has no owner-facing tooling. The v1 owner surface is constrained to the read-only spec in `product-design/02-frontend-design.md §7.3`, `product-design/03-workflows.md` flow 14, and `product-design/05-improvements-over-original.md` improvement #15 — bookings, statements, redacted guest info, simple block-requests. The four expansion axes in this mockup (multi-user owner-org, change-request approval queue, owner-driven onboarding, in-portal messaging) are deferred. See `../10-decisions.md` "Deferred" table. Do **not** implement these expansions without re-opening the decision.
>
> Source: https://vc-owner-portal.netlify.app/
> Reviewed against: `django_res_design/workflows/`, `django_res_design/product-design/`
> **Headline:** ~70% covered by product-design improvements; legacy has almost nothing. The mockup goes meaningfully beyond the spec on (a) owner-initiated edits with a VC approval queue, (b) multi-user owner-org accounts with internal RBAC, (c) owner-driven property onboarding, (d) in-portal messaging. These are the four big new pieces.

---

## 1. Summary

The Villa Collective Owner Portal mockup is an SPA logged in as **Andreas Kostas**, an "Account Admin" for the owner organisation **"Kostas Hospitality Ltd"** (header strap: `"Owner · 4 properties · 3 users"`). The shell has seven primary nav items — Dashboard, My Properties, Bookings, Availability, Finance, Messages (3 unread), Users & Permissions — and a property detail with eleven tabs (Overview, Rooms, Features, Nearby, Rates, Finance, Images, Descriptions, Settings, Contacts, Change history). Almost every owner-side mutation flows through a **"submit for approval / pending VC"** queue rather than writing directly to the live model. The product-design spec (`product-design/02-frontend-design.md:725-737` §7.3 Owner Portal, `product-design/03-workflows.md:657-693` flow 14, `product-design/05-improvements-over-original.md:98-107` improvement #15) anticipates *some* of this — owner block-requests, statements, redacted guest info, per-property notification settings — but **not** the broader editability surface, the multi-user owner organisation, the messaging thread model, or the owner-side onboarding-approval path.

Coverage estimate against existing design docs:

- **Read-only views (Dashboard, Bookings list, Statements/Finance, Availability calendar):** ~90% covered conceptually by flow 14 and improvement #15 — implementation detail only.
- **Owner edits to property data (rates, descriptions, bedrooms, features, photos, settings):** **net new** — flow 14 explicitly frames owner as read-only outside of block requests and notification preferences (`03-workflows.md:669` "Read-only version of flow 10. Owner sees Booked / Hold / Unavailable…").
- **Approval queue / "pending changes":** **net new** — no `ChangeRequest`-shaped entity exists in `01-domain-model.md`.
- **Multi-user owner organisation with RBAC:** **net new** — current model is `Contact` + `MagicLink` (`01-domain-model.md:312-314`, `04-rest-api-surface.md:607` `/contacts/{id}:invite-portal`), single-user-per-owner-contact.
- **In-portal messaging:** **net new** — no `Thread` / `Message` model exists.
- **Owner-driven property onboarding flow:** **net new** — flow 12 (`product-design/03-workflows.md:557-602`) is explicitly admin-only.

**Top 5 "this is new" callouts:**

1. **A `ChangeRequest` / approval-queue mechanic across nearly every property edit** — peak rate, photos, descriptions, bedrooms, features, settings, even nearby places. Banner strings recur: *"Changes queue for VC approval"*, *"Submitted for approval"*. The mockup shows a withdrawable, line-itemised submission ("Pending changes · Villa Anemoi" modal, lines 1799–1842 of the source HTML).
2. **Owner = company, not person.** "Kostas Hospitality Ltd" is the account; Andreas Kostas, Maria Kostas, Sophia Liakos (a third-party property manager), James Trent (external accountant) all log in as members with distinct roles: Admin / Property Manager / Finance / Editor / View only. This is a multi-tenant relationship the current data model doesn't have.
3. **Owner-driven property onboarding** (Villa Ariadne flow). VC prepares the listing; the owner approves it to go live. The reverse of `03-workflows.md` flow 12, which is purely operator-initiated. Lines 1844–1876 of the source.
4. **First-class in-portal messaging** between owner-org members and named VC staff (Sophie Lambert, David Henley), threaded, linkable to a booking or property, with read/unread state.
5. **Per-property "Pending changes" surfacing** on the dashboard, property card, and property-detail banner — visible everywhere, not just in a hidden inbox. The dashboard "Pending your attention" card shows three classes of pending item: onboarding-awaiting-owner, unread messages, owner-hold-awaiting-VC.

---

## 2. Identity & access model — biggest divergence

The current spec treats an owner as a single `Contact` with optional portal access:

- `01-domain-model.md:275-278` — *"Contact: Owner, manager, agent, accountant, supplier — anyone other than the booking-side guest… No `password` etc. — Contacts are not auth users; if they need portal access, a `User` row is linked with a `contact` FK."*
- `01-domain-model.md:312-314` — *"MagicLink: For owner-portal passwordless login. Fields: `email`, `token_hash`, `expires_at`, `used_at`, `created_for_contact` (FK)."*
- `04-rest-api-surface.md:607` — *"`POST /contacts/{id}:invite-portal` — Send owner-portal invite."*
- `04-rest-api-surface.md:101-102` — *"`POST /auth/magic-link:request` — Owner-portal passwordless link" / "`POST /auth/magic-link:consume`"*.
- `05-improvements-over-original.md:106` — *"Magic-link login option for low-volume owners (no password to forget)."*
- `02-frontend-design.md:728` — *"Owners get a separate shell under `/owner/*`. Same React app, different layout (simpler topbar, no Admin/Library sections). Server enforces that owners only see their own properties and that finance fields are filtered."*

The mockup instead models owners as a **company account** ("Kostas Hospitality Ltd", `"Owner · 4 properties · 3 users"`), with multiple human users sharing the account, each with an internal role and per-property access scoping. Concretely, the Users & Permissions screen (lines 1414–1516) lists:

| Avatar | Name | Role | Property access | Status |
|---|---|---|---|---|
| AK | Andreas Kostas (you) | **Admin** | All 4 properties | Now |
| MK | Maria Kostas | **Admin** | All 4 properties | 3 hours ago |
| SL | Sophia Liakos | **Property Manager** | Anemoi · Petalon (2 of 4) | Yesterday |
| JT | James Trent | **Finance** | Finance only · all properties | 1 week ago |
| PI | petros@inv-acc.gr | **Finance** (Pending invite) | Finance only · Petalon | invitation sent 2 days ago |

Role catalogue surfaced in the invite-user modal (line 1785) and in the role-permissions matrix (lines 1478–1513):

- **Admin** (also called **Account Admin** in copy at line 1417) — full powers including manage users, edit bank details, approve VC-submitted changes, restrict to specific properties = "Always all".
- **Property Manager** — view bookings, edit property info (VC-approval-gated), submit availability holds, messages. **No finance, no bank, no user management.**
- **Finance** (also rendered as "Finance Editor" in some places — invite modal lists "Finance"; permissions matrix column is "Finance") — view finance & statements, messages. **No property edits, no holds.**
- **Editor** — edit property info, submit availability holds, messages. No finance.
- **View only** — view bookings only.

UI strings cementing this:

- Banner on Users page (line 1417): *"Users & Permissions — invite team members, accountants, or property managers to access your portal. Set role-based permissions per user; restrict access to specific properties where needed. Only Account Admins can manage users."*
- Invite-user helper (lines 1789–1790): *"What this role can do: view bookings, edit property info (subject to VC approval), submit availability holds, send and receive messages. Cannot view finance, change bank arrangements, or manage other users."*
- Edit-user modal (line 1957–1964) shows a per-property checkbox list scoped under "Properties accessible".

**Implied domain entities (not in `01-domain-model.md`):**

```
OwnerOrganisation (e.g. "Kostas Hospitality Ltd")
  - name
  - billing_address / tax_number (implied; statements need them)
  - members (M2M via OwnerMembership)
  - properties (M2M via existing Property ↔ Contact mapping?
                or a new OwnerOrganisation FK on Property)
  - default_role_template (Admin/PM/Finance/Editor/View)

OwnerMembership
  - organisation FK
  - user FK
  - role: enum(ADMIN, PROPERTY_MANAGER, FINANCE, EDITOR, VIEW_ONLY)
  - property_access: enum(ALL) | M2M(Property)
  - invited_by, invited_at, accepted_at
  - status: enum(PENDING, ACTIVE, REMOVED)

OwnerInvite
  - email, organisation FK, role, property_scope, message, token_hash, expires_at, used_at
```

**Conflict with current spec:**

`01-domain-model.md:285-290` describes `ContactPropertyMapping.role` with an *operator-style* enum (`owner` / `manager` / `agent` / `concierge` / `accountant` / `read_only` / `viewer` / `custom`). That enum is about what role a *Contact* plays *vis-à-vis a Property*, used by ops to decide who gets notified for what. It is **not** an "owner-org member role" — those are different concepts, despite the name overlap. The new mockup needs a separate enum for owner-org membership role; reusing `ContactPropertyMapping.role` would conflate two unrelated permission frameworks.

`05-improvements-over-original.md:31-35` improvement #5 also describes role-preset compaction on `ContactPropertyMapping` — same point, same risk of conflation.

**Open question for product (see §9):** is multi-user owner-org actually wanted v1, or is v1 a single-contact-with-magic-link, with the org model deferred to v2? Mocked invite/edit/role-matrix screens read as a deliberate v1 design.

---

## 3. Screen-by-screen specification

### 3.1 Dashboard (`tpl-dashboard`, lines 418–508)

**Welcome banner (line 421):** *"Welcome back, Andreas. You have 2 properties live, 1 pending VC approval (onboarding), 3 unread messages, and €5,650 owed in your next payout."* + *"Take a tour"* button.

**KPI cards** (lines 425–430):

| Label | Value | Sub-label |
|---|---|---|
| YTD bookings | 11 | 9 cleared · 2 in progress |
| YTD revenue | €312,000 | Your share: **€249,600** |
| Utilisation | 68% | vs 54% last year |
| Next payout | €5,650 | due 15 May 2026 |

**Upcoming arrivals table** (lines 434–446) — three sample rows showing booking ref, property, guest, dates, status pill. Note that `VC4055 · Villa Cetinale · Mr Q. Davies` shows on the dashboard but later the booking-detail page shows the same booking on `Villa Anemoi` — a mockup data inconsistency rather than a deliberate design.

**Pending your attention card** (lines 448–467) — three rows:

1. *"Villa Ariadne — onboarding awaiting your approval — VC has submitted the property listing for your review. Approve to go live."* + **Review** CTA (opens approve-onboarding modal).
2. *"3 unread messages from VC — Latest: 'Confirming pool service for Villa Anemoi week of 8 May…' — Sophie Lambert"* + **Open inbox**.
3. *"Villa Anemoi — your availability hold for 22–28 May is awaiting VC approval — Submitted 2 days ago. VC typically responds within 1 business day."* + **View calendar**.

**Properties mini-list** (lines 470–495) — Villa Anemoi (Corfu, 4 bed, Live, €156k), Villa Petalon (Mykonos, 5 bed, Live, €156k), Villa Ariadne (Santorini, 6 bed, **Pending you**), Villa Selene (Crete, 8 bed, **Off-market**).

**Recent activity feed** (lines 497–505) — four entries, each with relative time + actor + verb, mixing owner-side actions ("Sophia Liakos updated bank details for Villa Petalon — went live immediately"), VC actions ("VC submitted Villa Ariadne for your review (onboarding)"), and money events ("VC released €8,750 commission payout to your bank account").

**Spec reference:** `02-frontend-design.md:731` lists `/owner/dashboard (my villas at-a-glance)` but does not enumerate KPIs or surfaces. `03-workflows.md:665` flow 14 step 1: *"Top cards: properties count, upcoming arrivals (next 30 days), occupancy % YTD, gross revenue YTD, net payout YTD."* — KPI set roughly matches, though mockup uses "Utilisation" and a "Next payout" amount-card instead of an occupancy %.

**Departure from spec:** the "Pending your attention" card is the central organising surface — it implies a notifications inbox concept (`Notification` model exists at `01-domain-model.md:422-423`, but no UI design for surfacing it has been written).

### 3.2 My Properties list (`tpl-properties`, lines 1081–1161)

Banner (line 1084): *"Your portfolio: 4 properties · 2 live on villacollective.com · 1 pending your approval · 1 off-market."*

Pill filter tabs: **All (4) | Live (2) | Pending approval (1) | Off-market (1)**. Sort dropdown: Name A–Z / Revenue YTD ↓ / Bookings YTD ↓ / Date added.

Top-right CTA: *"+ Add property (request)"* — note the *(request)* qualifier — owner cannot create directly; they request and VC fulfils, then the listing comes back through onboarding-approval (see §3.10).

Each property card carries: thumbnail tile, status pill (Live / Onboarding · awaiting your approval / Off-market), villa name, location + bed count + sleeps, and a 3-stat grid (YTD bookings, YTD revenue, Utilisation). The Villa Petalon card additionally shows *"3 changes pending"* — a propagated alert from a separate per-property approval queue.

**Spec reference:** `02-frontend-design.md:732` *"/owner/properties/:id (read-only or limited edit)"* — the "limited edit" hint exists but no list-page design appears in spec.

### 3.3 Property detail (`tpl-property-detail`, lines 510–1078)

Eleven tabs. Tab list (lines 531–543): **Overview · Rooms · Features · Nearby · Rates · Finance · Images · Descriptions · Settings · Contacts · Change history**.

Header banner when pending changes exist (lines 511–515): *"**3 changes awaiting VC approval** · weekly rates · 2 photos · marketing copy. Submitted 18 hours ago."* + link to view pending changes + *"Withdraw"* button. Header strip (lines 517–527) has *"Preview on website"*, *"View public listing"*, and *"Submit changes for approval"* actions.

Tab-by-tab summary:

**Overview** (lines 549–596) — KPIs scoped to this property, "Property snapshot" card (image, summary text, 4-key facts grid), "Upcoming bookings" list, "Owner notes from VC" (named VC staff posting time-stamped paragraphs visible to the owner).

**Rooms** (lines 599–624) — banner: *"Bedroom inventory used by VC for matching guest enquiries and generating quotes. Edits queue for VC approval."* Table of 4 bedrooms with name, bed configuration, features, placement (`Main House`), and per-row edit/delete icon-buttons. "+ Add bedroom" opens add-bedroom modal (banner: *"New bedrooms queue for VC approval before they appear on the live listing."* — lines 1693–1696). Bedroom fields: Name, Double/Twin-double/Twin/Single/Bunk/Sofa bed/Children's bed (count inputs), Ensuite (checkbox), Website description, Owner notes (visible to VC team only), Placement (Main House / Guest House / Annexe / Cottage). Plus a free-form description card.

**Features** (lines 627–743) — banner: *"All feature lists are visible on the public listing and used to match enquiries. Add/edit items in any category — changes queue for VC approval."* Six cards, each a category with a name+description table and "+ Add" button: **Living spaces, Indoor features, Outdoor features, Included features, Services on request, Collections**. Plus a card "Other information & tags" with selected tags (sample: Sea view, Family-friendly, Wedding-suitable, Wine country) and a free-text description.

"Add features" modal opens *"Add features · pick from library"* with category dropdown matching the cards, search box, and helper text (paraphrased from earlier extraction): *"Features are picked from a unified library maintained by VC, so listings stay consistent across the website. Can't find what you need? Request a new option and VC will add it to the library."* This implies a global feature library (the existing `Feature` model — `01-domain-model.md:85-93`) plus a **request-new-feature** path that doesn't exist in the spec today.

**Nearby** (lines 746–812) — banner: *"Tell guests what's around the property — towns, airports, beaches, restaurants, and supermarkets — with distances and travel times. Edits queue for VC approval."* Five sub-tables (Towns, Airports, Beaches, Restaurants, Supermarkets), each with columns: Name, Description, Distance (km), By boat (min), By drive (min), By walk (min). Add/edit nearby modal categories: Towns / Airports / Beaches / Restaurants / Supermarkets / Bars / Other.

**Rates** (lines 816–838) — banner if pending: *"1 rate change pending VC approval · Peak (Jul/Aug 2026) raised from €28,000/wk to €30,000/wk. Submitted 18 hours ago."* Header actions: *"Copy from 2025"* + *"+ Add rate period"*. Table columns: Season, Period, Min nights, Weekly rate, Status (Live / Awaiting VC), actions. Pending row shows strike-through old value → new value plus a small "Pending" pill. Six rows in the 2026 schedule (Low → Shoulder → Mid → Peak → Mid → Shoulder).

Edit rate period modal (referenced in mockup, fields per earlier extraction): Price (Net/Gross toggle), Commission, Tax, Currency (Euro/GBP/USD), Weekly/Nightly/Price POA, Occupancy pricing checkbox, Commission type (Percentage/Flat amount), Tax exempt + percentage, Discount applies, Arrival/Departure dates, Minimum night stay.

**Finance** (lines 841–907) — banner (line 844): *"Commission & payment-schedule terms are **set in your VC owner agreement** — contact us to amend. Bank details are **live** (no approval needed). Tax + security-deposit settings queue for VC approval."* Five cards:

- *Commission* — read-only, *"Read-only · contact VC to amend"*. Type Percentage, Amount 20% of gross rental, Notes (VC team only) "15% for repeat clients returning within 24 months."
- *Tax* — editable. Tax number EL137376771, Exempt Yes, Percentage 0%.
- *Payouts* — read-only. *"Bank details held off-platform · contact VC finance to update"*. Payout currency EUR (€), Payout method Bank transfer (held with VC finance), helper: *"For your security, we don't store your bank account details on this platform. Contact finance@villacollective.com to update where payouts are sent."*
- *Payment schedule* — read-only per owner agreement. Deposit required Yes, Type Percentage, Amount 30%, Interim required No, Days balance due before arrival 56, Statement frequency Quarterly.
- *Security deposit* — editable. Required Yes, Method Bank transfer (manual invoice), Amount type Percentage, Amount 10% of gross, Days invoiced before arrival 14, Days refunded after departure 14.

This is the **only place in the mockup that draws an explicit line between "live immediately"** (bank details — though paradoxically off-platform — and contacts) and "approval-gated" (tax, security deposit, everything else).

**Images** (lines 910 onward, continuing past the 935 read) — banner (line 913): *"2 photo additions pending VC approval · uploaded 18 hours ago. The current live gallery (24 photos) remains visible to guests until approved."* Drag-to-reorder grid with role tags ("1 · Hero", "2 · Int 1", "3 · Int 2", "4 · Ext 1", "5 · Ext 2"), and proposed-images shown with an amber border + Pending overlay until VC approves.

**Descriptions** (lines 938–990) — banner: *"Long-form copy used on the website listing and inside guest-facing PDFs. Edits queue for VC approval — VC may also rewrite for tone/brand consistency."* Five sections: Top description (Web description 1 / 2), Interior (sub-heading + paragraph), Exterior (sub-heading + paragraph), Location (sub-heading + paragraph), Video URL. Per-section *Edit* button opens an edit-description modal.

**Settings** (lines 993–1034) — banner: *"Operational settings that affect how the property is sold and how bookings are handled. Edits queue for VC approval since they impact pricing & availability behaviour."* Three cards:

- *Sales & availability* — Availability status (Available), Bookings require pre-approval (No · *VC confirms direct*), Prices entered are (Gross), Currency (EUR).
- *Check-in / check-out* — Check-in time 16:00, Check-out time 10:00, Changeover day Saturday, Min nights rental 7, Min nights notes.
- *Pricing & nightly rate* — Nightly price override (Not set — uses weekly rate ÷ 7), Lead time before arrival (3 days), Booking window (18 months ahead).

Edit-settings modal fields per earlier extraction: Check-in time, Check-out time, Changeover day (Saturday/Sunday/Friday/Flexible), Min nights rental, Min nights notes.

**Contacts** (lines 1037–1058) — banner: *"**Contact details go live immediately** — no VC approval needed. Use this for owner, on-site team, and emergency contacts that VC team and (where appropriate) guests can reach."* Optional *"Use group contacts"* checkbox (inherit from a property-group default). Table: Role pill, Name, Email, Phone, Primary, Live since, status. Sample row roles: Owner, Manager, Housekeeper, Pool / maintenance, Emergency. Roles available in add-contact modal: **Owner, Manager, Housekeeper, Pool / maintenance, Chef, Driver, Concierge, Emergency, Other**. Per-contact fields: Role, Primary contact for property (checkbox), First/Last name, Email, Phone, Spoken languages, Visible to guests? (checkbox; helper *"Yes (shared on welcome pack)"*), Notes for VC team.

**Change history** (lines 1061–1074) — append-only audit log of edits with actor + status pill (Pending VC / Live (auto) / Approved / Rejected). Filter dropdown: All changes / Pending only / Approved only / Rejected only. Sample entries include both owner-side ("You submitted availability hold (22–28 May 2026) — Pending VC") and VC-side ("VC · David Henley rejected change to commission split — out of scope of owner agreement — Rejected").

**Spec reference:** `02-frontend-design.md:730-732` enumerates owner property paths but says *"read-only or limited edit"*. The eleven-tab structure echoes the operator-side property detail (`02-frontend-design.md:200-229` §3.3 *"14 tabs collapsed to 6"*), but the owner-portal mockup goes the *opposite* direction — 11 tabs, not 6 — because the owner is shown one property at a time and benefits from finer surfaces.

### 3.4 Bookings list (`tpl-bookings`, lines 1163–1202)

KPI cards: YTD bookings (11), YTD gross revenue (€312,000), Average stay value (€28,400 vs €25,200 last year), Cancellations (0, 12-month rolling).

Pill tabs: **All (11) | Future (3) | Past (8) | Cancelled (0)**. Property filter dropdown, year filter dropdown, *"Export CSV"* action.

Table columns: **Reference, Property, Guest, Stay dates, Party, Gross, Your net, Status**. Sample row:
```
VC4055 · Direct · Villa Anemoi · Mr Q. Davies · 11 — 18 Apr 2026 · 7 nights · 6 adults · €56,500 · €45,200 · Deposit paid · Open
```
Source pills under the booking reference cell: `Direct`, `Direct · repeat`, `Agent · Premium`.

Status pills: Deposit paid (amber), Confirmed (live/green), Cleared (live/green).

Guest column shows full name in mockup — but the booking-detail page (§3.5) carefully restricts party/guest data per privacy policy. The list-level inconsistency is worth flagging: spec (`03-workflows.md:671` flow 14 step 4) requires *"guest initial"*-only display in list views.

### 3.5 Booking detail (`tpl-booking-detail`, lines 1518–1679)

Four tabs (owner-side): **Overview, Payments, Services & concierge, Notes from VC**.

Header (line 1522): `"VC4055 · Mr Q. Davies"` + status pill. Action buttons: *"Print PDF"*, *"Message VC about this booking"* (opens a message-thread modal — links into the messaging system).

**Overview tab** — KPIs: Gross value €56,500 (your net €45,200), Stay length 7 nights, Party 6 adults (no children), Days to arrival 4 days (arriving 16:00). "Stay summary" card: Property, Booking reference, Arrival, Departure, Source, Concierge tier (Signature). **"Guest snapshot" card** — explicitly labeled *"Limited info per privacy policy"* — shows: Lead booker (Mr Quentin Davies), Country (United Kingdom), Repeat client (Yes · 2nd stay with VC), Preferred contact (*"Via VC team only"*), Allergies / accessibility flags (*"Tree-nut allergy (severe)"*). Booking timeline at the bottom showing every state change with pill colour and pre-stay scheduled items.

**Payments tab** — KPIs (Gross €56,500, VC commission €11,300 (20%), Your net €45,200, Next payout 15 May 2026). Payment ledger table: Date, Description, Method, Amount, Status (Cleared / Invoice scheduled / Pending stay completion). Commission breakdown card.

**Services & concierge tab** — banner: *"Concierge services arranged for the guest. Owners can see what's on site and when. Payments for these services are handled separately by VC."* Table: Service, Supplier, Date/time, Status, Guest pays. Sample services: Airport transfer (arrival/departure), Welcome hamper, Private chef · 4 dinners (Tree-nut-free menu), Boat day. Plus an "On-site requirements" card with prose about what's expected from the on-site team.

**Notes from VC tab** — read-only, time-stamped paragraphs by named VC staff (Sophie Lambert, David Henley). Header note: *"Read-only · contact VC to add"*.

**Spec reference:**
- `03-workflows.md:670-671` flow 14 step 4 — *"redacted financial detail unless `view_full_money` permission, no internal notes"*. The mockup's Payments tab shows **gross, commission, owner net** in full, including a "Next payout" amount of €5,650 to a specific date. This is inconsistent with the flow-14 redaction principle and needs alignment.
- `05-improvements-over-original.md:105` improvement #15 — *"Redacted-by-default guest info (initials only) with per-permission unhide."* Mockup uses "Mr Quentin Davies" + "United Kingdom" + repeat flag, *not* initials-only. That said, contact channel is deliberately hidden (*"Via VC team only"*), so the spirit is partially honoured. Spec needs clarification: is the rule initials-only (`03-workflows.md:669`) or named-with-no-contact-channel (mockup)?

### 3.6 Availability (`tpl-availability`, lines 1204–1249)

Banner (line 1207): *"**Block dates you want held off the calendar** (owner stays, maintenance, family use). Click a date to add a hold; click again to remove. **Submitting changes notifies VC** — they'll be applied to the live calendar once approved (typically within 1 business day)."* CTA: *"+ Add hold"*.

Toolbar: property switcher, 3-month / 6-month / Year zoom toggle, prev/next month arrows.

Calendar legend (line 1224–1230) — five colour swatches:

- Booked guest (dark navy)
- VC hold (amber)
- Your hold (live) (mid-purple)
- Your hold (pending VC approval) (striped purple)
- Available (light green)

Below: a table *"Your holds — 4 active, 1 pending"* with columns Property, Dates, Reason, Submitted (relative time + actor), Status (Pending VC / Live), action (Withdraw / Edit). Sample reasons: Family use, Christmas — owner stay, Maintenance · roof repairs, Owner stay · winter.

Add-hold modal (lines 1746–1768) banner: *"Holds queue for VC approval before they're applied to the live calendar (typically within 1 business day). Guest bookings already on these dates will be flagged for VC to discuss with you."* Fields: Property, Reason (Family use / Owner stay / Maintenance / Renovation / Off-market period / Other), From, To, Notes for VC team.

Edit-hold modal (lines 1918–1942) banner: *"Editing a live hold submits the change for VC approval. The existing dates remain blocked until your edit is reviewed."* — note the explicit semantic that a *live* hold can be edited but stays in effect during VC review. Plus a *"Withdraw hold"* danger action.

**Spec reference:** `03-workflows.md:679-680` flow 14: *"Owner requests block (date range) → operator notification → flow 10 approval."* This matches the mockup, though the spec's hold semantics are richer (`01-domain-model.md:257-269` enumerates a 7-value `AvailabilityRecord.status` enum including `on_hold` and `unavailable` with a `reason` enum of `owner_stay / maintenance / closure`).

**Departure from spec:** the mockup adds **conflict-detection at submission time** ("Guest bookings already on these dates will be flagged for VC to discuss with you") — implied but not designed in `06-availability.md`. The mockup also adds a richer reason taxonomy (Family use, Owner stay, Maintenance, Renovation, Off-market period, Other) compared to the model's three.

### 3.7 Finance (`tpl-finance`, lines 1251–1298)

Four KPI cards (line 1253–1257): YTD revenue (gross) €312,000, Your net YTD €249,600 (*"80% / 20% split"*), VC commission €62,400 (*"paid to VC"*), Next payout €5,650 (*"due 15 May 2026"*).

Toolbar: property filter, year filter (2026 YTD / 2025 / 2024 / All time), *"Download statement (PDF)"*, *"Download CSV"*.

**Earnings by booking** card with sub-header *"Cleared bookings only · pending bookings appear once funds settle"*. Columns: Booking, Property, Stay, Gross, Comm. (20%), Your net, Status (Paid out / Awaiting clearance), Payout date.

**Payout history** card. Columns: Date, Period (Q1 2026 / Q4 2025 / Q3 2025 / Q2 2025), Bookings included ("2 (Mar)"), Net amount, Method (*"Bank transfer · NBG ••• 4421"* — masked bank reference), Statement (PDF link). Link *"View all 12 payouts ›"*.

**Spec reference:** `05-improvements-over-original.md:99-107` improvement #15 — *"PDF + CSV statements (accountants love CSV)"* — covered. `02-frontend-design.md:546-549` §3.15 Reports: *"Owner statements — picker (owner + period) → generated statement with line items per booking, payout summary, downloadable PDF."* Same intent.

**Departures from spec:**
- Mockup shows **two-axis report**: per-booking earnings vs per-period payouts. The current spec describes only the per-period statement.
- The "80% / 20% split" copy directly on the KPI card surfaces the **owner-org commission deal**. Currently `PropertyFinance.commission_*` fields exist (`01-domain-model.md:71`), but no design for displaying the split as a banner-level concept.
- The mockup does **not** show multi-currency UI for an owner with properties in different currencies. Both sample properties are in EUR. This is a gap to clarify — spec (`02-frontend-design.md:701-704` §6.4) demands `<MoneyDisplay>` always renders currency code; the mockup uses bare `€` symbols throughout.

### 3.8 Messages (`tpl-messages`, lines 1300–1412)

Two-pane inbox layout.

**Thread list (left pane)** — Search input + new-message button. Six threads in the sample:

| Avatar | Sender | When | Topic | Read state |
|---|---|---|---|---|
| SL (vc) | Sophie Lambert · VC | 11:42 | ▸ Villa Anemoi · maintenance | active/selected |
| DH (vc) | David Henley · VC | Yesterday | ▸ Q1 statement · all properties | unread |
| SL (vc) | Sophie Lambert · VC | 2 days ago | ▸ Villa Ariadne · onboarding | unread |
| EV | Eleni Vlachos (you) | 3 days ago | ▸ Villa Anemoi · maintenance | read |
| SL (vc) | Sophie Lambert · VC | 1 week ago | ▸ Villa Anemoi · edits | read |
| DH (vc) | David Henley · VC | 2 weeks ago | ▸ Villa Anemoi · enquiry | read |

**Thread pane (right)** — Header shows sender, sub-line *"Thread: Villa Anemoi · maintenance · 5 messages"*, actions *"Link to booking"* + *"Mark resolved"*. Body shows alternating bubbles labelled "Sophie Lambert · VC" vs "You", with date separators (*"— 5 May 2026 —"*, *"— Today —"*) and per-bubble timestamps. Compose box at bottom: textarea (*"Reply to Sophie… your message will be logged on this thread and visible to VC's team."*), link-to dropdown (*"Link to: Villa Anemoi" / "Link to: a booking" / "No link"*), Save draft, Send.

The threads have a **resolved state** (mark resolved button), a **topic** (free-text), an **entity link** (to property or booking), and per-user **read state**. One thread shows *"Eleni Vlachos (you)"* — an owner-side member, not VC — which means messaging is **not** strictly owner↔VC; the spec needs to clarify whether threads can be owner-team internal (probably not — likely all threads have a VC participant).

**Spec reference:** there is **no message/thread model anywhere** in `01-domain-model.md` or `04-rest-api-surface.md`. `01-domain-model.md:379-388` has `EmailTemplate` / `EmailLog` / `CodeAuthLog` and `Notification` (in-app, `01-domain-model.md:422-423`), but no thread/conversation entity.

The mockup messaging is meaningfully different from the existing `BookingNote` model (`01-domain-model.md:236-240`), which is single-author notes attached to a booking. Messaging is **two-party threaded conversation** spanning properties, bookings, and standalone topics. Likely a sibling concept to whatever the Client Portal (`02-client-portal.md` analysis) ends up specifying — see §5 for the shared-model proposal.

### 3.9 Users & Permissions (`tpl-users`, lines 1414–1516)

Already covered in §2. Two cards: an active-users table (line 1421) and a **role permissions matrix** (line 1475) presented as a reference grid:

```
Permission                              | Admin | PM | Finance | Editor | View only
View bookings                           |   ✓   | ✓  |    ✓    |   ✓    |     ✓
Edit property info (VC approval)        |   ✓   | ✓  |    ✕    |   ✓    |     ✕
Submit availability holds               |   ✓   | ✓  |    ✕    |   ✓    |     ✕
View finance & statements               |   ✓   | ✕  |    ✓    |   ✕    |     ✕
Edit bank details / payouts             |   ✓   | ✕  |    ✕    |   ✕    |     ✕
Send / receive messages                 |   ✓   | ✓  |    ✓    |   ✓    |     ✕
Approve VC-submitted changes (onbording)|   ✓   | ✕  |    ✕    |   ✕    |     ✕
Manage users & permissions              |   ✓   | ✕  |    ✕    |   ✕    |     ✕
Restrict to specific properties         | Always all | ✓ | ✓     |   ✓    |     ✓
```

The matrix is described as *"Reference — what each role can do"* — suggesting roles are **fixed code-defined enums**, not editable per organisation. This parallels the operator-side decision at `01-domain-model.md:303-307`: *"`User.role` is a hard-coded enum, not a row in a table."*

### 3.10 Property onboarding — Villa Ariadne (modal `approve-onboarding`, lines 1844–1876)

Modal title: *"Review & approve · Villa Ariadne (onboarding)"*. Banner: *"VC's team has prepared this listing on your behalf. Review the details below and approve to take it live, or request changes."*

Read-only field grid:

- Display name: Villa Ariadne
- Internal ref: VC-009
- Location: Pyrgos, Santorini, Greece
- Sleeps: 12 in 6 bedrooms
- Bathrooms: 6
- Pool: Heated infinity (12m)
- Headline (full-width): *"A six-bedroom Cycladic estate above the caldera, with private chef and infinity pool"*
- Short description (full-width)
- Proposed peak rate: €48,000 / week
- Commission split: 80% / 20% (per agreement)

Footer: *"Request changes"* + *"Approve & go live"*. Trailing info box: *"Once you approve, the listing goes live on villacollective.com and VC starts taking enquiries. Any future edits you make will queue for VC approval as normal."*

**Compare to admin-side flow 12** (`03-workflows.md:557-602`):

- Flow 12 is a **9-step wizard for ops to build a property from scratch**: Basics → Location → Rooms → Features → Pricing → Contacts → Images → Policies → Publish, with `Draft` lifecycle.
- The owner-onboarding modal is the **owner-side gateway** at the *end* of that wizard — VC builds the property, then routes it for owner sign-off **before** the publish step actually flips `Property.status` to `active`.

This means flow 12's step 9 ("Publish") splits into two phases under the owner-onboarding model:
1. Ops reaches "ready for owner" → property enters a new `pending_owner_approval` status.
2. Owner approves → property becomes `active` and goes live.

Currently `Property.status` enum is `draft | active | archived` (`01-domain-model.md:65`). The mockup implies a fourth state, or a separate `pending_owner_approval` boolean flag orthogonal to status — to be designed.

**Net new top-level action endpoints implied:**

- `POST /owner/properties/{id}:approve-onboarding` — owner approves a pending listing; flips to active.
- `POST /owner/properties/{id}:request-changes` — owner sends back with comments.
- `POST /owner/properties:request-new` — owner-side intake stub (the *"+ Add property (request)"* button at line 1085).

---

## 4. The "pending changes" / approval queue

This is the **central mechanic** the mockup invents — and the largest gap relative to the current design. Every owner-side edit to a live property creates a `ChangeRequest` that VC then approves or rejects. The mechanic appears in many places; one consolidated view at the *"Pending changes · Villa Anemoi"* modal (lines 1799–1842) makes the shape concrete:

```
3 changes submitted 18 hours ago · awaiting VC approval.
You can withdraw the entire submission or withdraw individual items.

| What changed       | Old                    | New                       | Submitted by   | Action     |
| Peak rate          | €28,000 / wk           | €30,000 / wk              | Sophia Liakos  | [Withdraw] |
|   (29 Jun — 30 Aug 2026)
| Photos             | —                      | 2 new images uploaded     | Sophia Liakos  | [Withdraw] |
|   (Gallery additions)
| Marketing copy     | "Daily housekeeping…"  | "Daily housekeeping,…"    | Sophia Liakos  | [Withdraw] |
|   (Service inclusions paragraph)

[Withdraw all]                                                                    [Close]
```

Banner copy that recurs across modals (lines 1693–1696, 1752–1755, 1885–1887, etc.):

- *"Changes queue for VC approval. You'll receive an email confirming submission, and another when VC approves or comments."*
- *"New bedrooms queue for VC approval before they appear on the live listing."*
- *"Holds queue for VC approval before they're applied to the live calendar (typically within 1 business day)."*
- *"Rate changes queue for VC approval. Existing live rate remains in effect for new bookings until approved."*
- *"Description edits queue for VC approval. VC may also rewrite for tone/brand consistency before publishing."*
- *"Editing a live hold submits the change for VC approval. The existing dates remain blocked until your edit is reviewed."*

The **change history** tab (lines 1061–1074) is the read-side: an append-only audit of all changes — owner-submitted, owner-direct (e.g. contacts), VC-approved, VC-rejected.

**Status taxonomy (pills):**

- `Live` — the change is in effect / item is on the live listing.
- `Live (auto)` — change went live without VC review (only used for **contact details** and **bank details**, per banner copy at lines 1040 / 844).
- `Pending VC` (also written `Awaiting VC`) — submitted, awaiting VC review.
- `Approved` — VC said yes; usually transitions to Live within seconds.
- `Rejected` — VC said no, with explanatory note (sample: *"out of scope of owner agreement"*).

**Withdrawal states:**

- Withdraw a single line of a multi-line submission → that line is voided; siblings remain pending.
- Withdraw the entire submission → all lines voided.

**No analog in either `workflows/` or `product-design/`** — entirely new. The closest existing concept is `BookingChange` audit (`03-workflows.md:268` *"booking timeline gets a change-log entry with before/after diff"*) and the operator-side concurrency-diff modal (`05-improvements-over-original.md:66`), but neither is a *proposal* model — both are *after-the-fact* records.

**Implied entities:**

```
ChangeRequest
  - id, property FK (or scope: property | rate-card | nearby | image | ...)
  - submitted_by (User FK, an owner-org member)
  - submitted_at
  - status: enum(PENDING, APPROVED, REJECTED, WITHDRAWN, SUPERSEDED)
  - reviewed_by (VC User FK, nullable)
  - reviewed_at, review_comment
  - approves_to_live_at (when VC approves, an effective-from timestamp)

ChangeRequestItem (one row per field/object touched)
  - change_request FK
  - target_kind: enum (
      PROPERTY_FIELD, RATE_CARD, RATE_RULE, BEDROOM, FEATURE_ATTACH,
      NEARBY_POI, IMAGE, DESCRIPTION_SECTION, SETTINGS_FIELD, TAX_FIELD,
      SECURITY_DEPOSIT_FIELD, ...)
  - target_id (nullable — null when creating new)
  - operation: enum(CREATE, UPDATE, DELETE, REORDER, REPLACE)
  - diff_payload (JSON — before/after for UPDATE; full body for CREATE)
  - item_status: enum(PENDING, APPROVED, REJECTED, WITHDRAWN)
  - reviewed_by, reviewed_at, review_comment

ApprovalEvent (append-only, one per state transition on a ChangeRequest or Item)
  - change_request FK
  - item FK (nullable — null when batched at request-level)
  - actor User FK
  - actor_side: enum(OWNER, VC)
  - kind: enum(SUBMITTED, WITHDRAWN, APPROVED, REJECTED, COMMENTED, AUTO_APPLIED)
  - at (timestamp)
  - notes
```

**Audit trail requirement:** all changes — including the **"Live (auto)"** path for contacts and bank details — flow into a single `AuditLog` (already in spec at `01-domain-model.md:418-420`) so the change-history tab can show both gated and un-gated edits in a unified feed.

**Per-mockup, the gated vs ungated split is:**

| Surface | Gating |
|---|---|
| Bedrooms (add/edit/delete) | Approval-gated |
| Features (add/edit/delete + reorder + categorise) | Approval-gated |
| Nearby places | Approval-gated |
| Rates (seasons + weekly rate) | Approval-gated |
| Images (add/reorder/delete) | Approval-gated |
| Descriptions (long-form copy) | Approval-gated, *plus VC may rewrite* |
| Settings (check-in/out, changeover, min nights, lead time, booking window) | Approval-gated |
| Tax, Security deposit | Approval-gated |
| Availability holds (owner-side) | Approval-gated |
| **Contacts** (owner, manager, housekeeper, etc.) | **Live immediately** |
| **Bank details / payouts** | "Live" (but actually held off-platform — see §3.3 Finance card; effectively delegated to VC finance) |
| **Commission, payment schedule** | **Read-only** (set by owner agreement) |

---

## 5. Implied data model additions

Reconciled against `product-design/01-domain-model.md`. Items below are *not currently modelled*.

### 5.1 OwnerOrganisation cluster (see §2)
`OwnerOrganisation`, `OwnerMembership`, `OwnerInvite`. Adds a new top-level multi-tenant axis on the **owner side** that's separate from `Site` / `PropertyGroup`. Properties currently relate to owners via `ContactPropertyMapping.role=owner` — this needs to become `Property.owner_organisation FK` (or M2M for co-owned villas). The `User` model needs to know which org(s) the user belongs to.

### 5.2 Approval queue cluster (see §4)
`ChangeRequest`, `ChangeRequestItem`, `ApprovalEvent`. Polymorphic over targets (Property, RateCard, RateRule, PropertyRoom, PropertyFeature, NearbyPOI, PropertyImage, PropertyDescription, PropertySettings, PropertyFinance subset, AvailabilityRecord) so a single inbox can serve VC ops.

### 5.3 Messaging cluster (see §3.8)
`Thread`, `Message`, `MessageRead`, `ThreadParticipant`. Likely shared with the Client Portal's messaging surface (see sibling analysis doc `02-client-portal.md`) — guest↔VC and owner↔VC fit the same shape.

```
Thread
  - id, topic (free text), subject_property FK (nullable), subject_booking FK (nullable),
    organisation FK (when on owner side), guest FK (when on client side),
    status: enum(OPEN, RESOLVED, ARCHIVED), created_by User, created_at, resolved_by, resolved_at

Message
  - thread FK, author User FK, body (rich text), attachments JSON, is_draft, sent_at

MessageRead
  - message FK, user FK, read_at  (composite PK)

ThreadParticipant
  - thread FK, user FK, side: enum(OWNER, GUEST, VC), added_at
```

### 5.4 On-site property contact (richer than `ContactPropertyMapping`)
`OnsitePropertyContact` — driver, chef, concierge, emergency, with visibility-to-guests flag and spoken languages. The existing `ContactPropertyMapping` (`01-domain-model.md:283-294`) is operator-facing permission/notification metadata; the on-site contact is **operational data shown in the guest welcome pack**. Sample fields from add-contact modal (lines 1989–1998):

- `role` (Owner / Manager / Housekeeper / Pool-maintenance / Chef / Driver / Concierge / Emergency / Other)
- `is_primary_for_property` (bool)
- `first_name`, `last_name`, `email`, `phone`
- `spoken_languages` (free text, e.g. "Greek, English")
- `is_visible_to_guests` (bool — *"shared on welcome pack"*)
- `notes_for_vc_team` (free text)

This may be modellable by extending `Contact` + `ContactPropertyMapping` with a new role enum and a few new fields, but the operator-side mapping (a `Contact` *role* per *Property*) conflates two things — the property's *operational on-site team* (cleaner, chef, driver, emergency) versus the property's *governance contacts* (owner, manager, accountant). The mockup uses *role pill colours* to distinguish them (Owner = purple, Manager = blue, Housekeeper = amber, Pool/maintenance = grey, Emergency = red). A new `OnsitePropertyContact` model dedicated to operational data may be cleaner than expanding `Contact`.

### 5.5 OwnerHold extension to `AvailabilityRecord`
`AvailabilityRecord.reason` already has `owner_stay | maintenance | closure` (`01-domain-model.md:257`). The mockup adds **richer reason taxonomy**: Family use / Owner stay / Maintenance / Renovation / Off-market period / Other. Also adds:

- `submitted_by` (the owner-org user)
- `submitted_at`
- `status` (pending VC / live)
- `notes_for_vc_team`
- linkage back to a `ChangeRequest` row

In other words an "owner-initiated availability hold" is effectively a `ChangeRequest` targeting an `AvailabilityRecord`. The auto-expiry semantics (`01-domain-model.md:268`) still apply to ops-side holds; owner holds are usually long-dated stays, not transient holds.

### 5.6 PropertyFeatureRequest
For the *"Request a new feature option"* path (Features tab, add-features modal): owners can ask VC to add a new option to the global feature library. Implied as a sibling of `ChangeRequest` but pointing at the **catalogue**, not at a specific property's attachment:

```
FeatureLibraryRequest
  - requested_by User
  - category (matches Feature.category enum)
  - proposed_name
  - rationale ("Why this would be useful")
  - suggested_description
  - status (PENDING, ADDED, REJECTED)
```

### 5.7 OwnerStatement & Payout
Statements are referenced multiple times: *"Q1 owner statement issued"*, *"Download statement (PDF)"*, *"15 Apr 2026 · Q1 2026 · 2 (Mar) · €38,400 · Bank transfer · NBG ••• 4421 · PDF"*. The existing model `01-domain-model.md:404-413` has `ReportRun` + `ScheduledReport` + generic `Export`, but no `OwnerStatement` / `Payout` first-class objects. The mockup implies:

```
OwnerStatement
  - organisation FK (or per-property FK)
  - period (Q1 2026 / month / custom)
  - generated_at, file_key
  - status (DRAFT, ISSUED, SUPERSEDED)

Payout
  - organisation FK
  - amount_currency, amount, paid_at, method (bank-transfer / other)
  - bank_account_masked (e.g. "NBG ••• 4421")
  - statement FK (the OwnerStatement that justifies the payout)
  - bookings (M2M Booking — which bookings rolled up into this payout)
```

(Bank account stored *off-platform* per the Finance card disclaimer — the masked tail is fine to persist; the full IBAN sits with VC finance.)

---

## 6. Implied API surface additions

Reconciled against `product-design/04-rest-api-surface.md`. Items below are not currently in the spec.

### 6.1 Owner organisations & members

```
GET    /owner-orgs/{id}
GET    /owner-orgs/{id}/members
POST   /owner-orgs/{id}/members:invite
PATCH  /owner-orgs/{id}/members/{member_id}
DELETE /owner-orgs/{id}/members/{member_id}
POST   /owner-orgs/{id}/members/{member_id}:resend-invite
POST   /owner-orgs/{id}/members/{member_id}:revoke
```

The shape mirrors `04-rest-api-surface.md:645-657` `/users` but is **scoped to an organisation**, not global. The owner-portal `User.role` (Admin/PM/Finance/Editor/Viewonly) is a *different* enum from the operator-side `User.role` (`01-domain-model.md:303-306` — Admin/Reservations/Accounts/Viewer). Two separate enums on the same model or a polymorphism on top of `User` — design decision.

### 6.2 Change-request approval queue

Owner side (submission/withdrawal):

```
POST   /owner/properties/{id}/change-requests       (submit one or many items as a batch)
GET    /owner/change-requests                       (list mine)
GET    /owner/change-requests/{id}                  (detail)
POST   /owner/change-requests/{id}:withdraw         (whole)
POST   /owner/change-requests/{id}/items/{item_id}:withdraw  (per-line)
```

VC side (review):

```
GET    /change-requests                             (cross-org inbox; admin)
GET    /change-requests/{id}
POST   /change-requests/{id}:approve                (apply all)
POST   /change-requests/{id}:reject                 (with comment)
POST   /change-requests/{id}/items/{item_id}:approve  (per-line approve)
POST   /change-requests/{id}/items/{item_id}:reject
POST   /change-requests/{id}/items/{item_id}:revise   (VC tweaks before approving — described in the Descriptions banner copy "VC may also rewrite for tone/brand consistency")
```

### 6.3 Owner-scoped property edit endpoints

Today's `04-rest-api-surface.md` exposes `PATCH /properties/{id}` etc. Owners *cannot* call those — their writes must go through change-requests. Two design options:

- **Option A: separate owner-scoped paths** — `POST /owner/properties/{id}/rooms` writes a `ChangeRequestItem(target=BEDROOM, op=CREATE)` instead of a `PropertyRoom`. The HTTP shape mirrors the operator-side resource, but the *semantics* are queue-and-wait.
- **Option B: same paths, different auth scope** — `POST /properties/{id}/rooms` with owner scope returns 202 and a `change_request_id` instead of 201 and the created resource.

Option A is more honest about the semantic distinction. Option B is fewer endpoints. The mockup doesn't reveal which path the frontend takes — to decide.

### 6.4 Messaging

```
GET    /owner/threads                                (list)
POST   /owner/threads                                (create new)
GET    /owner/threads/{id}                           (detail)
PATCH  /owner/threads/{id}                           (link to booking/property, topic, mark resolved)
GET    /owner/threads/{id}/messages
POST   /owner/threads/{id}/messages                  (send)
POST   /owner/threads/{id}/messages/{msg_id}:edit    (edit own draft — likely not allowed once sent)
POST   /owner/threads/{id}:mark-read
POST   /owner/threads/{id}:mark-resolved
POST   /owner/threads/{id}:archive
GET    /threads                                      (VC-side cross-org inbox)
```

### 6.5 Property onboarding (owner-driven request + owner-side approval)

```
POST   /owner/properties:request-new        (the "+ Add property (request)" flow)
GET    /owner/properties/onboarding         (list pending-approval onboardings)
GET    /owner/properties/{id}/onboarding    (detail — the Villa Ariadne modal data)
POST   /owner/properties/{id}:approve-onboarding   (flip to active)
POST   /owner/properties/{id}:request-onboarding-changes  (route back to VC with comments)
```

Implies a new `Property.status` value (or sibling boolean) for "VC-prepared, awaiting owner approval" — see §3.10.

### 6.6 Feature library requests

```
POST   /owner/feature-requests              (request a new option be added to the global library)
GET    /owner/feature-requests              (list mine)
```

VC-side counterparts under `/feature-requests` for triage.

### 6.7 Statements & payouts (owner-facing)

```
GET  /owner/statements                       (list across all my properties / period filter)
GET  /owner/statements/{id}                  (detail)
GET  /owner/statements/{id}/pdf
GET  /owner/statements/{id}/csv
GET  /owner/payouts                          (list)
GET  /owner/payouts/{id}                     (detail)
```

Spec has `/reports/owner-statements` and `/reports/owner-statements/{contact_id}` (`04-rest-api-surface.md:687-690`) — these are operator-side report endpoints. Owner-facing endpoints differ: they're scoped automatically, paginate per-organisation, and need explicit PDF/CSV resources.

### 6.8 On-site contacts

The mockup *"On-site contacts"* surface (line 1043) is richer than the existing `ContactPropertyMapping`. Either extend the existing path:

```
GET    /properties/{id}/onsite-contacts
POST   /properties/{id}/onsite-contacts
PATCH  /properties/{id}/onsite-contacts/{contact_id}
DELETE /properties/{id}/onsite-contacts/{contact_id}
```

…or add a flag to `ContactPropertyMapping` distinguishing "on-site operational" from "governance" mappings.

---

## 7. Conflicts with existing specs

1. **Editability scope** — `03-workflows.md:669-672` flow 14 frames owner as **read-only** outside of block requests and notification preferences. The mockup makes the owner a **broad editor** of rates, descriptions, photos, bedrooms, features, settings, with VC approval as the gate. This is the single biggest design shift.

2. **Identity model** — `01-domain-model.md:312-314` + `04-rest-api-surface.md:101-102` model owners as **single `Contact` + magic-link**. Mockup models them as **`OwnerOrganisation` + multiple `User` members with RBAC**. The magic-link concept may still apply to invited members, but the data model needs a new `OwnerOrganisation` axis.

3. **Property onboarding ownership** — `03-workflows.md:557-602` flow 12 is **admin-only**. Mockup adds an owner-driven *intake* (the *"+ Add property (request)"* button at line 1085) and an owner-side **approval gate** at the end of the flow (lines 1844–1876).

4. **Feature taxonomy** — `01-domain-model.md:85-93` describes `Feature` as VC-curated with `is_active`. Mockup adds an owner-side *"Request a new feature option"* path (Add-features modal copy quoted earlier), implying a `FeatureLibraryRequest` workflow that's net new.

5. **Messaging** — no `Thread` / `Message` model exists anywhere in spec. `BookingNote` (`01-domain-model.md:236-240`) is single-author, append-mostly notes attached to a booking; the mockup's threaded conversation with read state is a different concept.

6. **Booking-detail redaction** — `03-workflows.md:669` says owners see *initials only* for guests by default. Mockup shows full names (`"Mr Q. Davies"`, `"Mr Quentin Davies"`) with country and repeat-status, hiding only the contact channel (*"Via VC team only"*) and the booking-internal-notes. The "redacted by default" rule needs refinement: is it initials-only (spec) or named-with-contact-redacted (mockup)? They're meaningfully different from a GDPR standpoint.

7. **Multi-currency display** — `02-frontend-design.md:701-704` §6.4 mandates `<MoneyDisplay value currency />` always render the ISO code (`£12,400 GBP`). Mockup uses bare `€` symbols throughout. For a UK owner with both Greek and Spanish villas, the mockup as-is gives no signal which currency a value is in. Tighten in implementation.

8. **`Property.status` enum** — spec is `draft | active | archived` (`01-domain-model.md:65`). Mockup implies a fourth state for *"VC-prepared, awaiting owner onboarding-approval"* (Villa Ariadne) and shows an *"Off-market"* status (Villa Selene) that may or may not map to `archived`. Reconcile.

9. **Rate-card model** — `02-frontend-design.md:232-262` §3.4 describes a complex three-level model (Season → RateCard → RateRule) with occupancy bands, discount rules, etc. The owner-portal Rates tab (lines 822–838) flattens this to **named seasons with a single weekly rate per season** — Low, Shoulder, Mid, Peak, Mid, Shoulder. Either: (a) the owner sees a simplified view that hides the rule-level detail (recommend, with edits scoped accordingly), or (b) the spec's three-level model is overkill for what the business actually needs. Worth confirming with product.

---

## 8. Notifications & email touchpoints

The mockup implies a richer set of owner-facing emails than `01-domain-model.md:379-388` (`EmailTemplate` / `EmailLog`) currently anticipates. Pulled from explicit banner copy and implied by state transitions:

- **Owner-org member invitation** — *"Invitations are emailed to the address below. The recipient creates their own password — you don't need to share one."* (line 1779).
- **Change-submission acknowledgement to owner** — *"You'll receive an email confirming submission, and another when VC approves or comments."* (line 1886).
- **Change-approved / change-rejected notification to owner** — same banner copy plus the implied state transition on `ChangeRequest`.
- **Onboarding listing ready for owner approval** — VC submits Villa Ariadne; the owner receives an email linking back into the approve-onboarding modal. ("VC submitted Villa Ariadne for your review (onboarding)" — Recent activity item, line 502).
- **Owner approval received** — VC notified when owner approves an onboarding or a booking.
- **Owner approval needed for booking** — `03-workflows.md:701-735` flow 15 already covers this case (`Booking.status = pending_owner_approval`).
- **Statement ready** — *"Hi Andreas — your Q1 2026 owner statement is now ready in the Finance section. Net €38,400 hits your account on the 15th…"* (Messages thread, line 1323).
- **Payout released** — *"VC released €8,750 commission payout to your bank account."* (Recent activity, line 503).
- **New booking on my property** — implied (flow 14 "notify_on_new_booking" already exists per `03-workflows.md:182`).
- **Booking change/cancellation on my property** — implied.
- **Conflict detected on hold** — *"Guest bookings already on these dates will be flagged for VC to discuss with you."* (add-hold banner copy, line 1754) — implies a notification path back to the owner once VC reviews and flags.
- **New message in inbox** — three unread message badges throughout the UI imply an email-or-in-app fan-out from the messaging system.

`01-domain-model.md:425-426` `NotificationPreference` lets the owner toggle topics per channel. The mockup doesn't expose a notification-prefs UI directly (the owner-portal sub-paths in spec at `02-frontend-design.md:730-735` don't include `/owner/notifications`), but `03-workflows.md:672` flow 14 step 6 demands per-property toggles — to be wired into a settings/profile screen.

---

## 9. Open questions for product

1. **Is multi-user owner-org actually wanted in v1, or is it v2?** The mockup commits to it heavily (Users & Permissions screen, role matrix, invite flow, per-property access), but v1 could plausibly land single-user-per-contact + magic-link as currently specced, with the org model deferred. Decision: if multi-user is v1, every endpoint and screen needs an `OwnerOrganisation` axis from day one.

2. **Approval queue mechanics — line-level or all-or-nothing?** The mockup shows both: *"Withdraw all"* (bulk) plus per-line *"Withdraw"* buttons. On the VC side, should VC be able to approve 2 of 3 items in a submission? Recommend yes — line-level review with all-or-nothing as a one-click shortcut.

3. **Owner-edit scope — where does owner authority end?** Mockup makes rates editable (under VC review) but commission read-only. Is this the line? What about:
   - Property's core identity (legal name, address, capacity)? Mockup shows these as part of onboarding-approval but not in the regular edit surface.
   - Property's `category` / `property_group` / `collections` membership?
   - `is_active` / `status` flip (e.g. owner wants to take their villa off-market) — currently spec has no owner-side path for this; mockup status `Off-market` for Villa Selene exists but no UI to set it.

4. **Messaging — shared model with guest portal, or separate?** Both portals will need owner↔VC and guest↔VC threading. The data shape is the same (Thread + Message + ThreadParticipant + sides {OWNER, GUEST, VC}). Recommend one model, three participant sides, one set of endpoints with scope filtering.

5. **Owner-driven property onboarding — full self-serve or lead-capture-then-VC-builds?** The mockup's flow is the latter: the *"+ Add property (request)"* button submits a stub; VC builds the listing; owner approves at the end. This is the **opposite** of `03-workflows.md` flow 12, which is fully VC-driven. Decision needed on the intake form fields and whether owner can edit during VC's drafting phase.

6. **Where do staff / on-site contacts live?** Today `Contact` + `ContactPropertyMapping` mixes owner/manager/accountant (governance) with housekeeper/chef/driver/emergency (operational on-site). Should we split these into two models? Mockup uses the same table for both but with distinct role pill colours.

7. **The booking-detail Payments tab shows full financial detail to the owner** — including commission breakdown and owner net. Flow 14 step 4 (`03-workflows.md:670-671`) describes per-permission `view_full_money` gating. Is the mockup an Admin-role view, with Property-Manager and Finance roles seeing different subsets? Permissions matrix says "View finance & statements: Admin ✓ / PM ✕ / Finance ✓ / Editor ✕ / Viewer ✕" — so PMs would *not* see this view. Confirm.

8. **Rate model — owner-facing flat vs operator-facing rich.** Mockup hides the spec's Season→RateCard→RateRule three-level hierarchy and exposes seasons-with-weekly-rate only. Is this a presentation-layer simplification (recommended) or should the underlying model be simpler?

9. **"Live (auto)" for bank details is paradoxical.** The Finance card (line 870) says payout bank details are *"held off-platform · contact VC finance to update"* — but the recent-activity feed shows *"Sophia Liakos updated bank details for Villa Petalon — went live immediately"* (line 500). Either the bank-details audit log records ops-side updates done by VC-finance staff on behalf of the owner, or there *is* an on-platform bank-detail update path that contradicts the Finance-card warning. Resolve.

10. **What does "Submit changes for approval" submit?** The property-detail page header has a *"Submit changes for approval"* button (line 525). Is this a *batch-submit-all-pending-drafts* button (which implies a per-property draft state where edits sit before being submitted), or just a navigation shortcut to the pending-changes modal? The cleaner mental model is the former: every edit creates a *draft* change-request item; the owner reviews their drafts and submits the batch when ready. The mockup's per-tab banner copy (*"Changes queue for VC approval"*) suggests immediate submission on save. Pick a model and stick to it.

---

## 10. Implementation notes for the engineering team

Independent of product decisions above, a few implementation hooks worth flagging up-front:

- **Reuse `AuditLog` as the change-history backing store.** Per `01-domain-model.md:418-420`, `AuditLog` already records `before` / `after` JSON + correlation id + actor. A `ChangeRequest` can be a *staged* `AuditLog` that doesn't apply until VC approves. The "Live (auto)" path writes straight to `AuditLog`; the "VC-gated" path writes to a `ChangeRequest`, then to `AuditLog` on approval.
- **The mockup uses `data-modal` attributes on rows to open modals.** That's fine for a static prototype; the React SPA per `02-frontend-design.md:130-136` uses `?drawer=...` URL params, which gives shareable deep-links to a half-open state. Use drawers rather than full modals for the bigger edit surfaces (edit-bedroom, edit-rate, approve-onboarding, pending-changes).
- **Per-property `ChangeRequest` count surfacing.** The dashboard card, properties list cards, and property-detail header all show pending-change badges. Cheap if computed via a single `COUNT(*) WHERE status=PENDING GROUP BY property_id` query and cached.
- **Optimistic UI for "Live (auto)" actions** (contacts, bank-details metadata) — these can update locally without awaiting server confirmation. Approval-gated edits need awaited submission so the banner can immediately show *"Submitted for approval"*.
- **Messaging — start with polling.** Per `02-frontend-design.md:663-665`, websockets are deferred. A 60-second poll on `/owner/threads?unread=true` is fine for v1, plus refetch on window focus.
- **Multi-currency owner**: when an owner-org has properties in different currencies, the Finance KPIs need to be either (a) normalised to a base with explicit display ("YTD revenue €312,000 EUR + £40,000 GBP normalised €380,000"), or (b) split per-currency on the dashboard. The mockup ducks the question by giving Andreas only EUR properties.

---

## Appendix A — Sample mock data quoted from the source

For context, the mockup commits to specific personas, properties, and numbers. Keeping these as canonical test data avoids the design team and engineering team diverging on examples:

**Owner organisation:** Kostas Hospitality Ltd — Greek hospitality company. Andreas Kostas (Account Admin). Maria Kostas (Admin). Sophia Liakos (Property Manager, third-party PM company). James Trent (Finance, external accountant). Petros (pending invite).

**VC staff visible to the owner:** Sophie Lambert (VC Sales / VC team), David Henley (VC team).

**Properties:**
- Villa Anemoi · Kassiopi, Corfu, Greece · 4 bed · sleeps 8 · 4 bath · 40m pool · Saturday changeover · YTD €156k / 5 bookings / 71% utilisation · live.
- Villa Petalon · Mykonos, Greece · 5 bed · sleeps 10 · YTD €156k / 4 bookings / 62% utilisation · live.
- Villa Ariadne · Pyrgos, Santorini, Greece · 6 bed · sleeps 12 · 6 bath · heated infinity (12m) · proposed peak €48,000/wk · 80/20 commission · onboarding awaiting owner approval.
- Villa Selene · Chania, Crete, Greece · 8 bed · sleeps 16 · off-market.

**Sample bookings:** VC4055 (Mr Q. Davies, 11–18 Apr 2026, Villa Anemoi, €56,500/€45,200 net, Deposit paid); VC3692 (Mr & Mrs J. Singh, 15–22 Jul 2026, Villa Anemoi, Confirmed); VC4101 (Ms F. Al Maktoum, 3–10 Aug 2026, Villa Petalon, Confirmed); plus several cleared past bookings (VC3128, VC3491, VC3401, VC3322, VC2978).

**Sample financials:** YTD gross €312,000; owner net €249,600 (80%); VC commission €62,400 (20%); next payout €5,650 due 15 May 2026. Payout history: Q1 2026 €38,400 (15 Apr), Q4 2025 €84,200 (15 Jan), Q3 2025 €127,800 (15 Oct), Q2 2025 €122,000 (15 Jul). Bank: *"NBG ••• 4421"*.

**Sample owner agreement:** Commission 20% percentage of gross (15% for repeat clients within 24 months). Tax exempt (number EL137376771). Deposit 30%. Days balance due before arrival 56. Statements quarterly. Security deposit 10% of gross via bank transfer (invoice 14 days pre-arrival, refund 14 days post-departure).

**On-site team (Villa Anemoi):** Owner Mr Andreas Kostas, Manager Sig.ra Eleni Vlachos (Greek/English/Italian, on site Mon–Fri), Housekeeper Sig.ra Anna Russo, Pool/maintenance Mr Giorgio Lombardi, Emergency Local hospital.

---

*End of analysis.*
