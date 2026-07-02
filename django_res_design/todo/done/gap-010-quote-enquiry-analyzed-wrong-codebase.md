> **✅ RESOLVED (2026-07-02)** — normalized on `feat/gap-010-docs` (`bcc58dd`, `33516cc`).
> **Problem:** this was an errata/reference doc wearing a ticket's filename — the wrong claims it
> proved stood uncorrected in the live docs, and it couldn't retire while it was the only home of
> the corrected reference content. **Fix:** §§1–4a (provenance, trust map, corrected claims,
> 4-screen flow, mockup note) promoted to
> [`workflows/legacy-quote-enquiry-reference.md`](../../workflows/legacy-quote-enquiry-reference.md)
> — this file is now the historical record. Errata landed in the live docs: `workflows/README.md`
> stubs bullet fixed in place (§3.1); `transmission.md` render claim corrected and its open
> question struck (§3.3); `05-improvements-over-original.md` #7 re-grounded as UX-only (§3.4);
> target-UX caveats added to `product-design/02+03` (§5.4); GAP-005's baseline premise corrected
> (§5.3). §5.5 integrity sweep run: 07/08 workflow docs are clean — the only stub-mislabelling
> was the Known-stubs bullet in `workflows/README.md` (fixed in place). §5.1 ("trust the backend specs") is encoded in the
> reference doc's trust map; §5.2 had already shipped as GAP-038/039/042/043/044.

# GAP-010 — Quote/enquiry specs were analysed against the wrong (post-deletion) codebase

- **Severity:** Gap (documentation / spec-fidelity) — tracker + corrected reference
- **Source:** Verification of the legacy analysis against a *runnable* April-2025 build of
  `ResSystem/` (branch `pinned-2025-04-03`, commit `05c69ed`), prompted by the discovery that
  the quote generator runs in production but is absent from `ResSystem`'s `main` branch.
- **Status:** ~~Findings recorded here only~~ *(superseded 2026-07-02 — see the ✅ banner above:
  the errata have now been applied to the live docs and the promoted reference is indexed).*
  Originally deliberate: this doc was the single place the disagreement was surfaced, per
  CLAUDE.md "surface the disagreement; do not silently choose one side", and intentionally not
  added to `INDEX.md`.

---

## 1. Summary — what happened

`django_res_design/` was authored ~May 2026 (first design commit `2532955`, 2026-05-12) by
extracting behaviour from `ResSystem/` **while it was on `main`**. But the legacy app uses a
snapshot-commit workflow and is **not** a faithful mirror of production: the entire
enquiry → quote UI was **deleted from source in April 2025** (`cc734a5`) while continuing to run
in the deployed binary. So the analysis read a tree in which the quote/enquiry **Blazor pages did
not exist**.

The **backend service layer (`ResService.cs`) survived** the deletion. Consequence — the analysis
is **split-quality**:

- **Backend-side specs are sound** — grounded in real, surviving code.
- **The screen / UX / flow layer was reverse-engineered** from a tree missing the actual screens,
  and is in places demonstrably wrong (real pages called uncommitted stubs; a parity review
  benchmarked against the wrong screen; a "client-side render" claim that is actually server-side).

The real screens are now readable and runnable on branch `pinned-2025-04-03` (the last
self-consistent April-2025 snapshot, which aligns with the 24-Apr-2025 production DB snapshot).

### Blast radius (git-tracked inventory)

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
vs the same against `main`.

---

## 2. Sound — do NOT re-do (grounded in surviving `ResService.cs`)

These specs were derived from code that survived in `main`, so trust them (re-validate only if convenient):

- `workflows/07-enquiry/enquiry-intake.md` — `PostEnquireNew` / `sp_villaEnquire`, public vs staff
  branching by `User=="WEBSITE"`, fire-and-forget Zoho push, the two notification emails. Solid.
- `workflows/08-quotation/persistence.md` — `ResQuotation` / `sp_quotation_master`,
  `SaveQuotationDetails` / `sp_saveQuotationDetails`, commission math, denormalised client/agent snapshot.
- `workflows/08-quotation/transmission.md` — the **side effects** of send (`sp_updateEnquireStatus`=2,
  Zoho push, per-staff SMTP, CSS inlining) are correct. Its claim about *where the HTML is rendered*
  is **not** — see §3.
- `workflows/07-enquiry/enquiry-management.md` — `GetEqnuireDetails`, status setter. Correct backend;
  the *list-screen UX* is missing (§4).

> **Expected, not a defect:** the docs' line citations point at `main`'s drifted `ResService.cs`
> (e.g. transmission.md says `SentQuotation` is at `ResService.cs:4094-4156`; in the pinned tree it
> is at `ResService.cs:2725-2771`; persistence.md says `ResQuotation` at `:3985-4092`, pinned has it
> at `:2636-2723`). The line numbers differ because `main` is ~14 months ahead; the **SP names and
> behaviour match**. The drift is not the problem — the *missing pages* are.

---

## 3. The provably-wrong claims (verified against pinned source)

### 3.1 `workflows/README.md:36` — real pages called uncommitted stubs
> "Known stubs: several pieces are referenced in code but not committed — `AvailabilityCard`,
> `ConnectionTracker`, `ClientInfomation`, `AgentInfomation`."

**Wrong for `ClientInfomation` / `AgentInfomation`.** Both are **real, committed components** in the
prod lineage:
- `ClientInfomation.razor` (175 ln): client search (3+ chars) via `SearchClientByName`
  (`ClientInfomation.razor:158-166`), autofill on select, Title / first / last / preferred-contact
  radio (Email|Mobile) / email / phone / town / country / postcode / address.
- `AgentInfomation.razor` (220 ln): company search (2+ chars, `:154-160`), agent dropdown per company,
  full agent autofill via `GetAgentById` (`:167-181`).

They appeared "not committed" only because they were deleted from `main`. **Correct as-is:**
`AvailabilityCard` and `ConnectionTracker` *are* genuine stubs — never committed even at pinned —
so those `[STUB]` marks (and `workflows/06-availability/*`'s calendar `[STUB]` notes) stand.

### 3.2 `todo/gap-005-quotation-flow-parity.md:12-21` — wrong legacy baseline
> "Legacy `Booking.razor` (1,151 lines) is a single combined workspace: enquiry capture + quote
> pricing + … all at once. The rebuild deliberately splits this into enquiry → quotation → booking
> stages (design improvement #7)."

**Wrong premise.** The legacy quote flow was **never** a single `Booking.razor` screen — it was a
**four-screen flow** (§4). The parity review benchmarked the rebuilt quote flow against the *booking*
screen because the actual quote screens were missing from `main`.

Mitigating note: gap-005 still surfaced many **genuine** gaps (preview-before-send, property imagery,
copy-to-Outlook, per-line discount, inclusions) — because `Booking.razor` is a *sibling* screen that
shares components (hero imagery `Booking.razor:91-92`, rich-text editor, pricing rows) with the quote
screens. So the conclusions were partly right by accident; the **structural baseline** was wrong.

### 3.3 `workflows/08-quotation/transmission.md:66-79` — render is server-side, not client-side
> "(Implicit) Render quote HTML for email … The Blazor `Content` value from the builder UI is already
> an HTML fragment … Push the entire render server-side in the Django redesign."

**Refuted.** The quote HTML is rendered **server-side** by `ResService.GetQuotationDetails`
(`ResService.cs:2566-2634`): it reads template `wwwroot/templates/quote-rate-lookup.html`
(`:2578`), runs `sp_getQuotationDetailsByQuotationId` (`:2579`), and replaces placeholders
`[#SRC#]`, `[#COUNTRY_REGION#]`, `[#VILLA_NAME#]`, `[#GUESTS#]`, `[#BEDROOMS#]`, `[#BATHROOMS#]`,
`[#ENSUITE#]`, `[#HEADER#]`, `[#DESCRIPTION#]`, `[#PRICING_AVALIABILITY#]` (`:2592-2616`). The Blazor
`ResEditor` (`RateLookup.razor:227`) only lets staff **edit** that server-rendered HTML before send.
The redesign recommendation "push the render server-side" is moot — it already is. (The Django
redesign's own server-side render seam, `reservations/services/quotation_render.py` from gap-005 F2,
is therefore the *right* shape and actually matches legacy — note that.)

### 3.4 `product-design/05-improvements-over-original.md` #7 — "worked one villa at a time"
> "**Was**: Quote-building UI was buried under 'Quotes & Enquiries → New Quote' and worked one villa
> at a time, with no clear cart-vs-search separation."

- "Buried under Quotes & Enquiries → New Quote" — **correct** (real navbar path).
- "Worked one villa at a time" — **questionable / likely wrong.** `QuoteGenerator` generates a
  **list** of villa options (`GetQuotationData` → `QuotationCard`), supports an **Add** button and
  manual villa rows, and persists **multiple** villa lines in one quote via
  `SaveQuotationDetails(List<QuotationDetailsArgs>)` (`QuoteGenerator.razor:834,888`); `RateLookup`
  groups the rendered quote **by villa id** for multi-villa output. Legacy supported multi-villa
  quotes; the weakness was the *cart-vs-search UX*, not single-villa capability. The "first-class
  multi-villa cart" improvement still stands as a **UX** improvement — just not because legacy was
  single-villa.

---

## 4. The real legacy quote/enquiry flow (corrected canonical spec)

Reconstructed from the pinned source. This is the screen/flow specification the original analysis
could not write. **Legacy was a 4-screen flow**, not one screen:

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

### What was genuinely missing/inferred and is now corrected
- The list screen (`/quote`) UX — columns, status circles, admin-only delete, navigation target.
- The multi-screen navigation chain itself (`/quote → /client-details → /quote-generator → /rate-look-up`).
- `ClientInfomation` / `AgentInfomation` / `PreferenceNotes` real behaviour (search, autofill, prefs).
- `RateLookup`'s two modes and the edit-server-HTML-then-send pattern.
- Villa hold placement from the quote builder (Status 40/10).

---

## 4a. Ben/owner mockup — the prospective target UX (2026-06-17)

The owner's Loom walkthrough pointed at a clickable mockup —
**https://vc-new-res-system.netlify.app/** ("the version that Ben and I
designed") — as the authoritative target for the enquiry list, the customer
profile, and the quote builder. It is **not** legacy source, but it
independently reproduces the real 4-screen flow from §4 (its Quotes & Enquiries
list columns — VC Ref / Name / Villa Name / Region / Enq/Quote Date / Sales
Person / Holiday Dates / Flex? — match the legacy `/quote` grid; its New-Quote
Overview mirrors the `ClientDetails` cards; its Rate Lookup mirrors the
weeks/occupancy model). Use it as the **target** UX reference alongside the
pinned legacy source. The screen/flow re-derivation called for in §5.2 is now
ticketed: [GAP-038](gap-038-enquiry-quote-stacking-conversion-metric.md),
[GAP-039](gap-039-enquiry-dashboard-enrichment.md),
[GAP-042](gap-042-customer-360-profile-view.md),
[GAP-043](gap-043-quote-builder-multi-week-range.md),
[GAP-044](gap-044-occupancy-band-fanout-builder.md).

## 5. Recommended follow-up

1. **Trust the backend specs** (§2); do not re-derive enquiry intake, persistence, transmission
   side-effects, or commission math.
2. **Re-derive the screen/flow specs** for `07-enquiry` (list screen) and `08-quotation`
   (construction/transmission UX) and the client-details capture flow from the pinned source — §4
   is the starting point.
3. **Re-frame gap-005** against the real 4-screen baseline rather than `Booking.razor`. Its concrete
   findings mostly survive; its "one screen → three stages" rationale does not.
4. Treat `product-design/{02,03}.md` as **target** UX (prospective), not legacy claims — they were
   not wrong about legacy, but they were designed believing the §3.2 baseline.
5. **Optional integrity sweep:** anything else in the workflow specs marked `[STUB]`/"not committed"
   that names a `Pages/Bookings/{Quotes,RateLookup,ClientDetails}/*` file is suspect for the same
   reason and worth a pinned-tree check.

## Verification

- Source citations resolve with `ResSystem` on branch `pinned-2025-04-03` (already checked out).
- Blast-radius table reproducible via the `git ls-tree` commands in §1.
- See memory `project_design_quote_analysis_codebase.md` and `project_ressystem_legacy_build.md`.
