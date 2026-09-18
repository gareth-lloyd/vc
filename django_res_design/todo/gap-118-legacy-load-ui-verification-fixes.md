# GAP-118 — Fixes from the 2026-09-18 UI verification of the legacy-loaded dev DB

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
