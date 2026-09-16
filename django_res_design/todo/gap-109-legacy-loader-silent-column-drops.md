# GAP-109 — Legacy loader: columns with real data that are dropped without a recorded decision

- **Severity:** 🟢 Gap (cutover fidelity). Each row is a one-line
  home-or-drop call; the ticket exists so none of them is decided by
  omission. Nothing here changes a guest price.
- **Rows 18–20 added 2026-09-16 (GAP-108).** Three columns the **ResProd**
  schema added since the 24-Apr-2025 dump, found while re-deriving
  `COVERAGE.md`. They are here so they are dropped by decision rather than by
  omission — the same reason the rest of this table exists. (`VillaFinance.
  SecurityDepositPaymentMethod`, found in the same pass, got its own ticket,
  **GAP-115**, because its codes cannot be decoded from anything we hold —
  folded back in 2026-09-16 as **row 21**, full text in §"Merged from
  GAP-115".)
- **Source:** 2026-09-11 legacy-loader audit — every registered loader's
  `legacy_query` diffed against `INFORMATION_SCHEMA.COLUMNS` on the
  24-Apr-2025 dump, then each ignored column counted for non-default values
  on **live** rows. Columns already recorded as dropped in `COVERAGE.md` /
  `CUTOVER.md`, or owned by another ticket (extras/discounts → GAP-107;
  per-rate commission/tax → BUG-028 §5; `IsSignup`'s Person linkage → BUG-030
  §22; WebDesc/Location split → GAP-090) are **not** repeated.
- **Files touched:** the loader named per row; `CUTOVER.md` §5 expected-loss
  list; `COVERAGE.md` "Notes"; target models under `django_res/<app>/models/`.

## How to use this ticket

Approve or amend the **Recommendation** column row by row when the ticket is
picked up. "Drop" means: add one line to CUTOVER's expected-loss list with the
count and reason. "Home" means: the named field, a transform test on a dict
fixture, and (where a count is derivable) a reconcile line.

## The table

| # | Source column(s) | Live rows with data | Loader | Recommendation |
|---|---|---|---|---|
| 1 | `VillaEnquire.DateType` — "+/- 3 days" ×8, "+/- 7 days" ×7, "Specific dates" ×14, "3" ×1 | 30 | enquiry | **Home** → `Enquiry.is_flexible` / `flexibility_days` (fields exist, never set). |
| 2 | `VillaEnquire.CountryId` where `RegionsId` is blank (178 resolve to a `VillaCountry`); 7 CSV `RegionsId` lists dropped whole | 233 / 7 | enquiry | **Home** → `region = unknown_region(country)` per the sentinel convention so the destination survives; CSV lists → first id + the rest in `inbound_message`. Today 422 enquiries lose their destination entirely. |
| 3 | `VillaEnquire.MaxBed` | 199 | enquiry | **Drop** — no target; `Enquiry` has party size, not bedroom count. Record. |
| 4 | `VillaEnquire.UserFeedback` ("how did you hear") | 5 | enquiry | **Home** → append to `inbound_message` with a label. |
| 5 | `VillaEnquire.IsSignup` | 301 | enquiry | **Home** → `Person.marketing_consent` once BUG-030 §22 links the Person; INV-006 #14 then closes. |
| 6 | `VillaQuotationMaster.EnquiryNote` (SELECTed, unused) / `PreferencesNote` / searched `FromDate`–`ToDate` / `Minbed`/`Maxbed` / `CountryId`/`RegionIds` / `Guests` | 9 / 10 / 19 / — | quotation | **Home** for the two notes → linked enquiry's `inbound_message` (BUG-030 §29); **Drop** the rest — the line rows carry the real dates and villas. Record. |
| 7 | `VillaClientDetails.Country` free text ("US" ×3 with `CountryId=0`) / `RegionId` | 3 / 2 | client | **Home** → resolve "US" to the ISO row; drop the rest. (`ContactType` → BUG-030 §19.) |
| 8 | `VillaFinance.ParentId` → owner/agent finance template | 271 / 291 | property_finance | **Home** → resolve `PropertyFinance.contact` through the template's `ContactId` (the loader's contact/template merge at `finance.py:267-289` is dead on real data: 291/291 live rows have `ContactId NULL`; only 1/291 gets a contact today, via the fallback). Reconcile line: contact set on ≥ 271. |
| 9 | `VillaFinance.SecurityDepositCalculateFromId` (all 20) / `IsManualUpdate` (152) / `SeasonId` (676 per-season override rows) / `BankAccCounty` (1) | — | property_finance | **Drop** — constant, sync bookkeeping, and the per-season overrides that the OneToOne-PK shape cannot hold (docstring already says so). Record the 676. |
| 10 | `VillaMaster.ConciergeService` tier (1 ×165, 2 ×126) | 291 | property | **Decide with Nick** — COVERAGE claims a TextChoices home that does not exist. Concierge is M2-deferred (INV-006 #20); either add `Property.concierge_tier` now (cheap) or record the drop and re-derive from the archived dump later. Listed in Q-028. |
| 11 | `VillaPropertyImages.GallaryOrder` — 1–4 "featured grid" slot (`UploadImage.razor:61-74`) | 696 | property_image | **Home** → `PropertyImage.kind`/`sort_order` cannot express it; add `featured_slot` (nullable small int) or fold into `sort_order` ordering. Ask Ben/Mojo whether the website rebuild (GAP-106) wants a featured grid before choosing. |
| 12 | `VillaNearBy.ByBoat` / `ByDrive` / `ByWalk` minutes (`Distance` is 0.0 on many of the same rows, e.g. all 7 for property 1) | 127 / 172 / 127 of 176 | nearby_place | **Home** → three nullable minute fields on `PropertyNearbyPlace` (the legacy screen labels them "Min. Boat/Drive/Walk"); or fold into `notes`. Distance-only loses the useful half. |
| 13 | `VillaCurrency.IsAfter` (USD symbol-after) / `CurrencyOrder` / `IsDefault` | 1 / 4 / 1 | currency | **Drop** — `IsDefault` is the `PropertyDefaults` currency (BUG-028 §3), the others are display concerns the FE owns. Record. |
| 14 | `UserMaster.Smtp*` per-user SMTP | 2 | user | **Drop** — same reasoning as `VillaConfigEmail` (secrets don't ride a migration); record next to it in COVERAGE §5. |
| 15 | `VillaSeasonRate.Name` (57 differ from the season name) / `IsAvailable` (3 False) / `TotalNight` (all 0) | 1 339 / 3 / 0 | rate_rule | **Drop** — a band has no name in the new model; `IsAvailable` false on 3 past rows. Record. |
| 16 | `VillaFeaturesMappings.CategoryId` (per-assignment category) / `Description` (per-villa tag override) | 535 | property_feature | Already noted in COVERAGE "Notes" as a GAP-067 follow-up — **no action here**; listed so the table is complete. |
| 17 | `VillaContactMapping.RoleMappingId` (selected, unused) / `VillaMaster.Channel`, `SettingAvailabilityStatusId`, `SettingPricesEnteredTypeId` (selected, unused or hardcoded) | — | assignment / property | **Tidy** — drop from the SELECTs (BUG-030 §4). |
| 18 | `VillaMaster.AvailabilityType` / `.AvailabilityValue` — **new in the ResProd schema**; across the 387 non-deleted villas `AvailabilityType` is NULL ×222, 1 ×102, 2 ×63 | 165 | property | **Decide** — the two codes are not decoded and there is no lookup table; ask the legacy developer before choosing. Likely **Drop** with the distribution recorded, but not by omission. |
| 19 | `VillaContactMapping.IsCC` — **new in ResProd**; marks a contact as copied on correspondence | 2 of 466 | assignment | **Drop** — 2 rows, and the new system models correspondence recipients per message, not per mapping. Record. |
| 20 | `VillaQuotationMaster.IsUnbrandedVilla` — **new in ResProd** | 87 | quotation | **Decide** — CHECK-005 lists `is_unbranded` as dropped from the Zoho quote payload, so a home may already be wanted there; settle both together. |
| 21 | `VillaFinance.SecurityDepositPaymentMethod` — **new in ResProd**; per-villa 0 ×59, 10 ×448, 20 ×1 (villa 489 "BT Test Villa"), plus 10 on all 413 templates and 676 per-season rows | 449 per-villa (non-zero) | property_finance | **Ask the legacy developer, then likely Drop** — the codes are undecodable from anything we hold (the column postdates `ResSystem/`, no lookup table in ResProd); do not guess "10 = bank transfer". Home only if 10 carries meaning the business relies on. Was GAP-115 — see §"Merged from GAP-115". |

## Acceptance

- Every row above is either a landed field with a transform test, or one
  line in CUTOVER §5's expected-loss list with the count.
- `COVERAGE.md` "Notes" gains a "silent drops audited 2026-09-11" line
  pointing here, and the `VillaConciergeServices` claim is corrected.
- Rows 10 and 11 have their owner/Mojo answer recorded in
  `design/decisions.md` (via Q-028).

## Dependencies

- **BUG-030** lands the enquiry Person link (row 5) and the notes fold (row 6).
- **Q-028** carries rows 10 and 11.
- **Legacy developer** (external) answers row 21 — ask in the same
  conversation as row 9.
- **GAP-107** owns extras/discounts; **GAP-090** owns the description-column
  split; **GAP-067** owns row 16.

---

## Merged from GAP-115 — `VillaFinance.SecurityDepositPaymentMethod`: three integer codes nobody can decode

> _Folded in 2026-09-16 (todo consolidation). The standalone ticket is closed as
> [GAP-115](done/gap-115-security-deposit-payment-method-codes-undecoded.md); the text below is that ticket as it stood, headings
> demoted one level. A reference to GAP-115 elsewhere now means this section._

- **Severity:** 🟢 Gap (cutover fidelity, low blast radius). The column is
  effectively constant on real data, so dropping it costs almost nothing —
  but it is being dropped by *omission*, which is what this ticket fixes.
- **Source:** GAP-108 dry run, ResProd (13-Aug-2026), measured 2026-09-16.
  One of the new columns the ResProd schema added since the 24-Apr-2025 dump.
- **Files touched:** `data_migration/loaders/finance.py` (only if the answer
  is "home it"); `COVERAGE.md` / `CUTOVER.md` §5 expected-loss list;
  `todo/gap-109-legacy-loader-silent-column-drops.md` row 9, which covers the
  column's neighbours.

### The facts

`VillaFinance` carries a `SecurityDepositPaymentMethod` int. Its whole
distribution on ResProd:

| Row kind | Code | Rows |
|---|---|---|
| per-villa (`SeasonId` NULL, `VillaId > 0`) | 0 | 59 |
| per-villa | **10** | **448** |
| per-villa | 20 | 1 |
| contact-default template (`SeasonId` NULL, `VillaId = 0`) | 10 | 413 |
| per-season (`SeasonId` set) | 10 | 676 |

(The three row kinds are the same ones the `PropertyFinance` reconcile gap of
1239 is itemised against — 413 templates + 676 per-season + 150 on excluded
villas. Do not collapse the templates into the per-villa count: they are not
a villa's own row.)

The single code-20 row is `VillaFinance.Id` 1531 on villa **489, "BT Test
Villa"** (`SecurityDepositAmount` 10) — test data, not a real policy. So on
real villas the column holds only 0 and 10.

**The codes cannot be decoded from anything we hold.** The column does not
exist anywhere in the in-repo `ResSystem/` checkout (it postdates it), there
is no lookup table for it in ResProd (`sys.tables` has no payment-method
table), and the ×10 spacing matches the legacy habit of hand-numbered enums
without a reference table. Guessing "10 = bank transfer" is exactly the kind
of invention that must not enter a migration.

### The decision this ticket exists to force

Ask whoever owns the legacy app (Nick/the ResSystem developer) what 0, 10 and
20 mean, then either:

- **Drop** — one line in the CUTOVER expected-loss list recording the
  distribution above and the fact that the codes were never decoded. This is
  the likely answer: one real value plus a blank, and the new system models
  the security deposit without a method field.
- **Home** — if 10 turns out to carry meaning the business relies on (e.g. it
  is the *reason* a deposit is collected pre-arrival rather than on the day),
  add the field with a transform test and a reconcile count.

Either way the answer gets written down, so the next audit does not re-ask it.

### Acceptance

- The meaning of 0 / 10 / 20 is recorded in `design/decisions.md` (or
  recorded as "asked, no answer available" — an explicit unknown beats a
  silent drop).
- The column is either loaded with a test, or named in `CUTOVER.md` §5's
  expected-loss list with its distribution.
- `COVERAGE.md` stops listing the column as unclassified.

### Dependencies

- **GAP-109** row 9 already covers the neighbouring `VillaFinance` drops
  (`SecurityDepositCalculateFromId`, `IsManualUpdate`, `SeasonId`,
  `BankAccCounty`). Fold this in when GAP-109 is picked up if the timing
  suits — it is the same conversation with the same person.
