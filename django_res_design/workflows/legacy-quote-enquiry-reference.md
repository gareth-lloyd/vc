# Legacy quote/enquiry flow — corrected reference (pinned April-2025 source)

The canonical description of the legacy quote/enquiry **screens and flow**, verified against a
*runnable* April-2025 build of `ResSystem/` (branch `pinned-2025-04-03`, commit `05c69ed`), plus a
trust map for the quote/enquiry workflow specs in this tree. Promoted from the investigation ticket
[GAP-010](../todo/done/gap-010-quote-enquiry-analyzed-wrong-codebase.md), which holds the full history of
how the original analysis went wrong; this document is the living copy.

**Why this document exists.** The workflow specs here were extracted from `ResSystem@main` — but
the legacy app uses a snapshot-commit workflow and `main` is **not** a faithful mirror of
production: the entire enquiry → quote Blazor UI was deleted from source in April 2025 (`cc734a5`)
while continuing to run in the deployed binary. The analysis therefore read a tree in which the
quote/enquiry pages did not exist. The backend service layer (`ResService.cs`) survived the
deletion, so the resulting specs are **split-quality**: backend-side specs are sound; the
screen/UX/flow layer was reverse-engineered and in places wrong. The corrections live here.

---

## 1. Provenance & blast radius

| Legacy file | Pinned `05c69ed` (real prod lineage) | `main` (what was analysed) |
|---|---|---|
| `Pages/Bookings/Enquires.razor` (`/quote` list) | ✅ committed | ❌ deleted |
| `Pages/Bookings/Quotes/QuoteGenerator.razor` | ✅ committed | ❌ deleted |
| `Pages/Bookings/RateLookup/RateLookup.razor` | ✅ committed | ❌ deleted |
| `Pages/Bookings/ClientDetails/ClientDetails.razor` | ✅ committed | ❌ deleted |
| `Pages/Bookings/ClientDetails/ClientInfomation.razor` (175 ln) | ✅ committed | ❌ deleted |
| `Pages/Bookings/ClientDetails/AgentInfomation.razor` (220 ln) | ✅ committed | ❌ deleted |
| `Pages/Bookings/ClientDetails/PreferenceNotes.razor` (62 ln) | ✅ committed | ❌ deleted |
| `NewResSystem.Core/Services/ResService/ResService.cs` | ✅ | ✅ **survived** |
| `Pages/Bookings/Booking.razor`, `BookingInfo.razor` | ✅ | ✅ survived |
| `Pages/Properties/Availability/Availability.razor` | ✅ | ✅ survived |
| `Components/AvailabilityCard.razor` | ❌ never committed | ❌ never committed |

Verify: `cd ResSystem && git ls-tree -r --name-only 05c69ed -- NewResSystem/Pages/Bookings`
vs the same against `main`. The pinned branch aligns with the 24-Apr-2025 production DB snapshot.

Line-number drift is expected and harmless: specs in this tree cite `main`'s `ResService.cs`
(e.g. `SentQuotation` at `:4094-4156`); the pinned tree has the same method at `:2725-2771`.
The **SP names and behaviour match** — only the missing pages were the problem.

## 2. Trust map — which quote/enquiry specs to trust

**Sound — grounded in surviving `ResService.cs`; do not re-derive:**

- [`07-enquiry/enquiry-intake.md`](./07-enquiry/enquiry-intake.md) — `PostEnquireNew` /
  `sp_villaEnquire`, public vs staff branching by `User=="WEBSITE"`, fire-and-forget Zoho push,
  the two notification emails.
- [`08-quotation/persistence.md`](./08-quotation/persistence.md) — `ResQuotation` /
  `sp_quotation_master`, `SaveQuotationDetails` / `sp_saveQuotationDetails`, commission math,
  denormalised client/agent snapshot.
- [`08-quotation/transmission.md`](./08-quotation/transmission.md) — the **side effects** of send
  (`sp_updateEnquireStatus`=2, Zoho push, per-staff SMTP, CSS inlining). Its render-location claim
  was wrong — corrected below (§3.3) and banner-noted in the file itself.
- [`07-enquiry/enquiry-management.md`](./07-enquiry/enquiry-management.md) — `GetEqnuireDetails`,
  status setter. Correct backend; the list-screen UX it could not describe is §4's `/quote` screen.

**Corrected claims (verified against pinned source):**

### 3.1 "ClientInfomation / AgentInfomation are uncommitted stubs" — wrong

Both are real, committed components in the prod lineage:
- `ClientInfomation.razor` (175 ln): client search (3+ chars) via `SearchClientByName`
  (`ClientInfomation.razor:158-166`), autofill on select, Title / first / last / preferred-contact
  radio (Email|Mobile) / email / phone / town / country / postcode / address.
- `AgentInfomation.razor` (220 ln): company search (2+ chars, `:154-160`), agent dropdown per
  company, full agent autofill via `GetAgentById` (`:167-181`).

They appeared uncommitted only because they were deleted from `main`. **Correct as-is:**
`AvailabilityCard` and `ConnectionTracker` *are* genuine stubs — never committed even at pinned —
so those `[STUB]` marks (and `08-quotation`/`06-availability` calendar `[STUB]` notes) stand.

### 3.2 "Legacy was one combined `Booking.razor` workspace" — wrong premise

[GAP-005](../todo/gap-005-quotation-flow-parity.md) (Source at `:4-7`, Context at `:22-30`)
benchmarked the rebuilt quote flow against the *booking* screen, because the actual quote screens
were missing from `main`. The legacy quote flow was never a single screen — it was the four-screen
flow in §4. Mitigating: `Booking.razor` is a component-sharing sibling (hero imagery
`Booking.razor:91-92`, rich-text editor, pricing rows), so GAP-005's concrete findings
(preview-before-send, property imagery, per-line discount, inclusions) mostly survive; its
structural baseline does not.

### 3.3 "Quote HTML is rendered client-side by Blazor" — refuted

The quote HTML is rendered **server-side** by `ResService.GetQuotationDetails`
(`ResService.cs:2566-2634` pinned): it reads template `wwwroot/templates/quote-rate-lookup.html`
(`:2578`), runs `sp_getQuotationDetailsByQuotationId` (`:2579`), and replaces placeholders
`[#SRC#]`, `[#COUNTRY_REGION#]`, `[#VILLA_NAME#]`, `[#GUESTS#]`, `[#BEDROOMS#]`, `[#BATHROOMS#]`,
`[#ENSUITE#]`, `[#HEADER#]`, `[#DESCRIPTION#]`, `[#PRICING_AVALIABILITY#]` (`:2592-2616`). The
Blazor `ResEditor` (`RateLookup.razor:227`) only lets staff **edit** that server-rendered HTML
before send. The Django redesign's server-side render seam
(`reservations/services/quotation_render.py`) is therefore the right shape and matches legacy.

### 3.4 "Legacy worked one villa at a time" — wrong

`QuoteGenerator` generates a **list** of villa options (`GetQuotationData` → `QuotationCard`),
supports an **Add** button and manual villa rows, and persists **multiple** villa lines in one
quote via `SaveQuotationDetails(List<QuotationDetailsArgs>)` (`QuoteGenerator.razor:834,888`);
`RateLookup` groups the rendered quote **by villa id** for multi-villa output. The rebuild's
"first-class multi-villa cart" improvement
([`05-improvements-over-original.md` #7](../product-design/05-improvements-over-original.md))
stands as a **UX** improvement (cart-vs-search separation) — not because legacy was single-villa.

---

## 4. The real legacy quote/enquiry flow (canonical)

Reconstructed from the pinned source. **Legacy was a 4-screen flow**, not one screen:

```
/quote  ──▶  /client-details  ──▶  /quote-generator  ──▶  /rate-look-up
(list)       (capture)             (build + price)        (review HTML + send)
```

### `/quote` — `Enquires.razor` (enquiry/quote list)
- Route: `Enquires.razor:1`.
- Grid columns: VC Ref, Name, Villa Name, Referral Code, Enq/Quote Date, Person, Holiday Dates,
  Flex? (`:83-96`). Status circle colours: `new` #ff487e, `completed` #0aa699, `opened` #dcc500,
  `pending` #ff00d8 (`:18-33,98-115`).
- Admin-only per-row delete (`:113`); non-admins blocked with a toast (`DeleteEnquire`, `:171-175`)
  → `DeleteEnquire` service (`sp_delete_enq` + Zoho deal delete).
- Row click → `OnQuoteNavigate` → `client-details` (new) or `/client-details/{enquiryNo}/{id}`
  (existing) (`:229-233`).

### `/client-details`, `/client-details/{EnquiryNo}/{Id}` — `ClientDetails.razor`
- Routes: `ClientDetails.razor:1-2`.
- **Card: Overview** — enquiry details (arrive/return dates, destination multi-country, regions,
  properties, children, adult, min/max bed, guest, referral, notes) + embedded
  `<ClientInfomation>` (`:28`, search enabled for new). Conditional **Agent block** (`@if IsAgent`,
  `:108`) with the agent checkbox shown only when `Id<=0` (`:97`) — embedded
  `<AgentInfomation>` (company search → agent select → autofill).
- **Card: Preferences & Notes** — `ResEditor` (`:225`) + preference checkboxes (`:228`);
  selected preference names are appended to `ClientNotes` on save (`:696`).
- **Cards: Previous Quotes / Previous Booking** — paginated history grids
  (`GetPreviousQuotes` / `GetPreviousBooking`); view → `/quote-generator/{no}/{id}` / `/booking/{no}/{id}`.
- Save → `ResService.ResQuotation` (`:563`) → navigates `/quote-generator/QUOTE/{quoteNo}/{quoteId}` (`:569`).

### `/quote-generator`, `/{QuotationNo}/{Id}`, `/{Type}/{QuotationNo}/{Id}` — `QuoteGenerator.razor`
- Routes: `QuoteGenerator.razor:1-3`.
- **Card: Client Information** — embedded `<ClientInfomation>` (no search, `:18`); agent block only
  when `QuotationNo<=0` (`:88`). Save → `ResQuotation` + `GetClientDetailsId` (`:619,625`).
- **Card: Quote** — arrive/return dates, destination, region, weeks (disabled if `IsSpecificDate`),
  guests, min/max bed, properties, features, unbranded-links. **Generate Quotes** → `GetQuotationData`
  (`:690`) → `<QuotationCard>` (`:292`). **Add** adds manual villa rows (`IsManual=true`, `:812-815`).
  **Save Quote** → `ResQuotation` + `SaveQuotationDetails` (`:884,888`, no navigation).
  **Send to client** → `SaveQuotationDetails` → `/rate-look-up/{no}/{id}/{clientId}` (`:834,837`).
- **Villa hold** from the results card: `PropertyService.ModifyVillaAvailability` with **Status 40**
  = place hold, **Status 10** = release (`:955,983`).
- `IsExist` / `Type=="BOOKING"` auto-regenerate on load and suppress the FromDate→+7d auto-shift
  (`:424-427,461`).
- Storage transforms: preferences and properties stored **comma-delimited** (`PreferenceId`,
  `Properties`, `:545,560`); weeks = `(ToDate-FromDate).Days / 7` (`Constant.RES_WEEK_DAY=7`).

### `/rate-look-up`, `/{no}/{id}`, `/{no}/{id}/{clientId}` — `RateLookup.razor`
- Routes: `RateLookup.razor:1-3`. **Two modes:**
  - **Review-and-send** (`QuotationNo>0`, `:201-240`): loads server-rendered HTML via
    `GetQuotationDetails` (`:527`) into an editable `ResEditor` (`:227`) prepended with a greeting;
    **Send Quote** → `SentQuotation` (`:997`).
  - **Generate-and-send** (`QuotationNo<=0`, `:241-478`): search → generate (`GetQuotationData`,
    `:706`) → `<QuotationCard>` → **Send Quote** → `SaveQuotationDetails` → `GetQuotationDetails`
    → `SentQuotation` (`:858-878`).

### Backend send (survived in `main`; behaviour confirmed at pinned)
- `GetQuotationDetails` — server-side template render (`ResService.cs:2566-2634`, §3.3).
- `SentQuotation` (`ResService.cs:2725-2771`): inline `quotation-rate-lookup.css`, wrap HTML, email
  via the staff member's SMTP profile, `EXEC sp_updateEnquireStatus {EnquireId},2`, then Zoho push.

---

## 5. Target UX reference — the Ben/owner mockup

The owner's Loom walkthrough (2026-06-17) pointed at a clickable mockup —
**https://vc-new-res-system.netlify.app/** ("the version that Ben and I designed") — as the
authoritative target for the enquiry list, the customer profile, and the quote builder. It is
**not** legacy source, but it independently reproduces the real 4-screen flow above (its
Quotes & Enquiries list columns — VC Ref / Name / Villa Name / Region / Enq/Quote Date / Sales
Person / Holiday Dates / Flex? — match the legacy `/quote` grid; its New-Quote Overview mirrors the
`ClientDetails` cards; its Rate Lookup mirrors the weeks/occupancy model). Use it as the **target**
UX reference alongside the pinned legacy source. The screen/flow re-derivation this enabled shipped
as [GAP-038](../todo/done/gap-038-enquiry-quote-stacking-conversion-metric.md),
[GAP-039](../todo/done/gap-039-enquiry-dashboard-enrichment.md),
[GAP-042](../todo/done/gap-042-customer-360-profile-view.md),
[GAP-043](../todo/done/gap-043-quote-builder-multi-week-range.md),
[GAP-044](../todo/done/gap-044-occupancy-band-fanout-builder.md).

Relatedly: treat [`product-design/02-frontend-design.md`](../product-design/02-frontend-design.md)
and [`product-design/03-workflows.md`](../product-design/03-workflows.md) as **target** UX
(prospective), not legacy claims — they were designed believing the §3.2 baseline.
