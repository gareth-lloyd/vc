# GAP-118 — Fixes from the 2026-09-18 UI verification of the legacy-loaded dev DB

> **✅ RESOLVED (2026-09-20)** — shipped on `feat/gap-118` as six commits,
> fast-forwarded into local `main` (unpushed).
>
> **The four product decisions.** §1 cards fetch **per column** (option (a)) —
> `useQueries` over `KANBAN_STATUSES` at `page_size=20`, with a "Showing N of
> M" footer and a "View all" link into the filtered list. §3 ships **both**
> halves: mint a Person per unmatched e-mail **and** render the sentinel as
> unlinked. §4 quote lines **do** borrow the party from the legacy enquiry. §2
> fixes `to_e164` **only** — no `PersonPhone` backfill command.
>
> **Units.**
> - `eeeabaaa` — §2: `to_e164` strips a spreadsheet `.00` tail.
> - `815fe7ab` — §4: `QuotationLineLoader` borrows the party from the legacy
>   `VillaEnquire` row when the master's `Adult`/`Children` are both NULL.
> - `c1073c10` — §3a: `relink_enquiry_customers --mint-unmatched`.
> - `3333b2b4` — §3b: read-only `is_unknown_client` on `ContactSerializer`;
>   `UNKNOWN_LEGACY_ID` / `CLIENT_LEGACY_PREFIX` / `UNKNOWN_CLIENT_LEGACY_ID`
>   move to `accounts/constants.py` (`accounts` cannot import
>   `data_migration`), re-exported from `loaders/sentinels.py`.
> - `8f9fc44d` — §3b (FE): the sentinel renders as "No customer linked" in
>   `CustomerProfilePanel`, in the quote builder's `EnquirySummaryHeader`, and
>   read-only in `DetailsTab`'s tags section.
> - `7df94e8c` — §1: per-column fetch + real badges.
>
> **D3a — the party comes from SQL, never the loaded ORM `Enquiry`.**
> `Quotation.enquiry` is `PROTECT` and not-null, and `Enquiry.adults` defaults
> to **2**; `ensure_enquiry()` never sets it, so every `…-autoenquiry` stand-in
> carries that default. Borrowing from the ORM would inject exactly the
> fabricated party of 2 that BUG-030 §23 bans. The legacy column is genuinely
> NULL-able, so SQL is the only honest source. §23 bans the `or 2` default, not
> a documented source — an explicit `Adult=0` still loads as 0.
>
> **D4 caveat — the acceptance line is met by a fresh load, not by the parser
> fix.** "0 `PersonPhone` rows match `\.0+$`" is not reachable on an
> *already-loaded* dev/staging DB: re-running `import_enquiry_sheet` never
> reaches `reconcile_primary_phone`, because of its `not person.phones.exists()`
> guard (`:177`). `Enquiry.phone` carries the same residue. That is acceptable
> because the cutover is a one-shot load into a fresh DB — the real cutover
> gets 0 rows for free, and dev/staging get it on their next rebuild. Recorded
> in `CUTOVER.md` §6h.
>
> **Deviations found while implementing** (each verified against the code, most
> as a failing test first):
>
> 1. **The `.0+` strip had to be conditional.** An unconditional
>    `re.sub(r"\.0+$", …)` regressed dot-separated numbers: `04.93.12.34.00`
>    (FR) stopped normalising and `+39 06.6982.0` became `+39066982` — a
>    different, valid, **wrong** number. `to_e164` is a live write path
>    (`wordpress_intake.py:206`), not just a loader helper, so the tail must be
>    the string's only dot (`fullmatch`).
> 2. **§6h's first stated mechanism was wrong.** `reconcile_primary_phone`
>    updates the PRIMARY row **in place**, so `unique_contact_phone` was never
>    why a loaded DB keeps its `.00` rows — the `not phones.exists()` guard is.
> 3. **The `VillaEnquire` join needs `AND e.DeletedAt IS NULL`.** Without it a
>    soft-deleted enquiry (which `EnquiryLoader` skips, so `QuotationLoader`
>    mints a stand-in) lends its party — "12A" lines under a 2-adult enquiry,
>    the inverse of §4's defect.
> 4. **Borrow when *either* enquiry field is positive, and leave a party above
>    32767 unborrowed.** `QuotationLine.adults` is a `PositiveSmallIntegerField`
>    and `VillaEnquire.Adult` is an unbounded web-form field; raising on write
>    would **drop** a line that used to load as 0A, turning this gap into a
>    cutover BLOCKER.
> 5. **§4's headline 1 235 is not the borrow count.** It counts zero-party lines
>    whose *loaded* `Enquiry.adults > 0` — a wider population (explicit
>    `Adult=0`, half-filled masters, stand-ins on the model default). Measure
>    the real figure from the `quotation_line_party_from_enquiry` log line on
>    the day. The reconcile residual row excludes stand-ins so its label is true.
> 6. **The planned case-insensitive pre-mint guard was dead code.**
>    `PersonEmail.email` is a `CIEmailField` (lowercased in `get_prep_value`,
>    citext-backed), so `classify_enquiry`'s lookup is already
>    case-insensitive: a mixed-case holder comes back `relinked` and can never
>    reach the mint pass. A test pins the real behaviour instead.
> 7. **The minted identity is assembled per field, not copied off one row.**
>    `(anon)` is dropped per FIELD (`(anon) Smith` → `"" / "Smith"`), a wholly
>    anonymous group takes the address as its first name (the
>    `find_or_create_person` rule — a nameless Person renders as "Client #id"),
>    and the phone comes from the lowest-id enquiry that has one INDEPENDENTLY
>    of the name pick, because nothing re-adds a dropped number. Two disagreeing
>    names on one address mint one Person and the unused name is reported.
> 8. **Mint-before-`_follow` is load-bearing.** `_follow`'s queryset filters
>    `enquiry__person__isnull=False` and is evaluated at call time, so minting
>    after it would strand the sentinel quotations and turn the **blocking**
>    `relinkable sentinel quotation` invariant RED.
> 9. **The sentinel needed guarding on three FE surfaces, not one.**
>    `EnquirySummaryHeader` (GAP-116 put the client's tags there *because* the
>    quote builder hides the rail) and `DetailsTab`'s **writable**
>    `InlineTagEditor` on `/clients/<sentinel>` both read the same
>    `useContact` route and would have contradicted the panel.
> 10. **The Kanban badge reads the column's OWN response, not
>     `status-counts`.** Each column request already returns the authoritative
>     `count` for the identical filterset; preferring the separate query opened
>     a window where badge, footer and cards disagree mid-invalidation.
>     `status-counts` stays the pre-load fallback and still feeds the list
>     view's `StatusFilterBar`.
> 11. **Fanning out tripled the board's failure surface.** `combine` reports
>     `isError` only when EVERY column failed; a single failed lane reports
>     itself in its own footer with a retry, so one transient 500 cannot
>     replace two perfectly good lanes with a full-width error.
>
> **Deliberately not done.** No `PersonPhone` backfill command (D4). Legacy
> image 404s stay with GAP-012. `QuotationListSerializer.guest_name` still
> renders "Unknown Client" — a separate surface. The SPA's
> `contactListItemSchema` strips `is_unknown_client`, so the Clients directory
> row still lists the sentinel as an ordinary customer; no list consumer needs
> the flag yet. `EnquiryFormDialog`'s contact picker still hydrates to the
> sentinel — nulling it would make a plain re-save silently clear
> `enquiry.person`, so unlinking wants an explicit affordance. Ambiguous
> sentinel cases (`shared_email` / `names_disagree` / `no_email` / `inactive`)
> are never minted, per GAP-112's non-negotiables. Both new `reconcile_legacy`
> rows are informational, not blockers. The Kanban stays read-only.

- **Severity:** 🟡 Gap (cutover fidelity + one frontend bug). No data is
  lost; each item makes loaded data display wrong or incompletely.
- **Source:** a read-only Playwright walk of every screen the load feeds,
  on the dev DB built by `CUTOVER.md` §4 (loadlegacy + sheets + relink +
  archive stays + relink, `reconcile_legacy --integrations` exit 0). The
  expected values were taken from legacy `ResProd` and the ORM with
  deterministic samples. `reconcile_legacy` passes. None of these is a
  count or an invariant, so no backend check could see them.
- **Not in this ticket:** the walk also found every legacy image 404ing.
  That is the unrun `import_legacy_images` step, already covered by
  [GAP-012](gap-012-s3-image-hosting.md) §Cutover runbook and `CUTOVER.md` §8.

Four independent units, each small. Numbers are from the 2026-09-18 dev DB.

## 1. Enquiry Kanban counts and cards come from page 1 only (frontend)

**Seen:** `/enquiries` (Kanban) shows **New 19** and **Quote sent 7**.
`GET /enquiries/status-counts` returns new 236, quote_sent 498,
progressing 1098 and dead 3249, and the dashboard's "New enquiries"
widget correctly shows 236.

**Cause:**
- `EnquiriesListPage.tsx` drops `page`/`page_size` for the board, with the
  comment "the board also isn't paginated". But the API always paginates
  (DRF `PageNumberPagination`, `PAGE_SIZE` 50), so the board receives the
  50 newest of 5 081 enquiries.
- `KanbanBoard` labels each column with `col.items.length`.
- Nothing was wrong on seeded data, because seeding makes fewer than 50
  enquiries.

**Fix:**
- Take the column badge from `useEnquiryStatusCounts` (already fetched on
  this page, with the same filters) instead of `items.length`.
- For the cards, pick one approach:
  - **(a)** fetch per column (`?status=<col>&ordering=-created_at`), with a
    "Showing N of M" footer and a link to the list view filtered by that
    status. This is the recommended option: it's bounded and every column
    stays correct.
  - **(b)** keep the one fetch but say the board shows the latest 50.
- Test: an MSW board with `count` > results shows the status-counts
  figure, not the card count.

## 2. 713 phone numbers end in `.00` (load)

**Seen:** 713 of 2 099 `PersonPhone` rows end in `.0`/`.00`, for example
`+44 7985414214.00`. 691 are on `sheet-person-…` people and 22 on legacy
`client-…` people.

**Cause:**
- The source cell in `Enquiries - FINAL.xlsx` is literally the **string**
  `+44 7985414214.00` (openpyxl type `str`, format General). The xlsx
  reader's integral-float coercion doesn't apply.
- `reservations.phone.to_e164` can't parse the string, so it returns the
  trimmed input unchanged (`to_e164('+44 7985414214')` gives
  `+447985414214`).

**Fix:**
- In `to_e164`, strip one trailing `\.0+` before parsing. This is
  deterministic and a real phone number never ends in `.0`. That covers
  `import_enquiry_sheet` (`:173`, `:257`) and `legacy_phone` in one place.
- Backfill the dev and staging DBs by re-running the imports, which are
  idempotent, or with a one-off pass that normalises each `PersonPhone`
  through the fixed `to_e164`.
- Test: `to_e164("+44 7985414214.00") == "+447985414214"`, and a genuinely
  unparseable string still passes through.

## 3. 546 enquiries with no customer, 51 quotes on the sentinel (load; decision)

**Seen:**
- 546 enquiries have `person = NULL`, 543 of them with an e-mail. By
  status: new 102, quote_sent 50, dead 362, progressing 32.
- 51 of them carry quotations on the unknown-client sentinel.
- Example: enquiry 1962 (Hannah Callaghan, hannahlcallaghan@gmail.com).
  Its detail page says "No customer linked", and QVC1962's guest is
  "Unknown Client".
- No `Person` anywhere holds that address, even after both relinks.
- The sentinel's Customer-profile panel renders it as an ordinary customer,
  with editable tags shared by all 51 quotes.

**Context:**
- [GAP-112](done/gap-112-post-load-customer-relink-for-enquiry-born-quotations.md)
  relinks only to people who already exist. It records "22 ambiguous + 31
  unresolvable stay on the sentinel" as not done.
- `CUTOVER.md` rejected minting a Person per enquiry *inside `loadlegacy`*,
  because the sheet import would then duplicate ~2 700 people. That
  objection doesn't apply **after** the second relink, for addresses no one
  holds.

**Decision needed.** The options can be combined:
- **(a)** A post-relink step, or a `relink_enquiry_customers` flag, that
  mints one customer `Person` per distinct unmatched e-mail. The name comes
  from the lowest-id enquiry with a name, and the phone from the same
  enquiry. It then links the enquiries and moves their sentinel quotes. It
  would be deterministic and idempotent on a `legacy_id` of
  `enquiry-person-<sha1(email)>`. Shared-address and names-disagree
  enquiries stay excluded, as in GAP-112.
- **(b)** Show the sentinel as "No customer linked" in
  `CustomerProfilePanel`, and hide tags and edits for it, whatever (a)
  decides.

## 4. Quote lines show a party of 0A where the enquiry has one (load; decision)

**Seen:**
- 4 046 of 7 692 `QuotationLine` rows are 0 adults and 0 children.
- **1 235** of those lines (253 quotes, created 2025-05-07 → 2026-08-12)
  belong to an enquiry with `adults > 0`.
- Example: QVC4216 shows "0A" on both lines, while enquiry 4216 records
  12 adults.

**Cause:** `QuotationLineLoader` takes the party from the master's
`Adult`/`Children`, and NULL becomes 0. BUG-030 §23/§27 ("never a
fabricated party") deliberately doesn't default to 2.

**Proposal (needs a call against §23):**
- When the master's party is NULL, fall back to the linked legacy
  enquiry's `Adult`/`Children`. That is recorded data, not an invented
  party, so it arguably meets §23's intent.
- Lines with neither stay 0.
- Log the count taken from the enquiry, like the GAP-108 borrow logs.
- Test: a master with a NULL party and a party on its enquiry takes the
  enquiry's party; both NULL gives 0.

## Acceptance

- Unit 1: the Kanban badges equal `status-counts` on the loaded DB.
- Unit 2: 0 `PersonPhone` rows match `\.0+$` after the backfill.
- Units 3 and 4: the decision is recorded here. If implemented, a
  `reconcile_legacy` report line gives the counts moved.
- Frontend and backend quality gates pass.
