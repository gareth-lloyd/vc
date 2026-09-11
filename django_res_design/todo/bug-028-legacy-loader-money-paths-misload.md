# BUG-028 — Legacy loader: every money-bearing path mis-loads (finance type codes, defaults, EUR row, zero-priced bands)

- **Severity:** 🔴 Bug (money — commission, deposits, security deposits,
  currencies and quoted prices are wrong on most migrated villas; the load
  exits 0 and `reconcile_legacy` passes because every check counts rows, not
  values).
- **Source:** 2026-09-11 legacy-loader audit (five parallel code-vs-dump
  audits + a full `loadlegacy --all` on a scratch DB
  `villacollective_loaderaudit`, 24-Apr-2025 dump). Every number below was
  read off that DB or the dump, not inferred.
- **Files touched:**
  - `django_res/data_migration/loaders/finance.py:48-59` (the three
    `_*_TYPE_MAP`s), `_finance_defaults`, `:267-289` (contact/template merge).
  - `django_res/data_migration/loaders/defaults.py:72-92` (same maps).
  - `django_res/data_migration/loaders/lookups.py:58-82` (`CurrencyLoader`),
    `django_res/data_migration/declarative.py:31-33` (generated query has no
    `ORDER BY`).
  - `django_res/data_migration/loaders/properties.py:190-215`
    (`_write_settings`).
  - `django_res/data_migration/loaders/pricing.py:86-99, 249-250, 258-264,
    479-484, 499, 534-543, 671`.
  - `django_res/properties/models/finance.py:34-56` (`_POLICY_FALLBACKS`),
    `django_res/pricing/services/engine.py:594-597, 623, 639-650, 791-815`
    (what the runtime actually reads).
  - `django_res/data_migration/management/commands/reconcile_legacy.py`
    (new value invariants).
  - Tests pinning the wrong shape: `tests/test_finance_contact_fallback.py:37,
    53, 61, 296, 312-318`, `tests/test_property_defaults_loader.py:31-49,
    66-67`, `tests/test_rate_band_loader.py:107-113`.
  - `django_res/data_migration/CUTOVER.md` §4 (the IsDefault deferral note),
    `DRYRUN_LOG.md` loader bugs 5–6.

## Problem

Four independent defects, all on the paths that decide what a guest pays and
what an owner receives. They compound: a villa can hit all four.

### 1. Finance type-code maps are keyed 1/2; legacy codes are 10/20

`DepositType` (`10 Percentage / 20 Fixed`) and `Enums.cs` `ECommissionType`
(`Percentage=10, Fixed=20`) are the real scale. Live rows carry 10 or 20
exclusively (`CommissionTypeId` 10×287, `PaymentScheduleDepositTypeId` 10×291,
`SecurityDepositAmountTypeId` 10×~170 / 20×~90). The loader maps `{1, 2}`, so
every `put()` is skipped.

Scratch DB after load: `commission_calculation_type` and
`security_deposit_calculation_type` are **NULL on all 291** `PropertyFinance`
rows. The model's fallback for security deposit is FIXED, so **49 live villas
that store "10 % security deposit" charge a fixed €10–€25**. `PropertyDefaults`
lands with `security_deposit_calculation_type=fixed, amount=10.00`, so every
villa created after cutover inherits the same error.

CUTOVER §4 lists the "commission/deposit type-code re-key (10=Percentage /
20=Fixed)" as built on `feat/legacy-loader` and NOT landed. The consequence
was never recorded, and the test fixtures use codes 1/2, so the suite is green
against a shape the dump never has.

### 2. `IsDefault*` / zero-value resolution is deferred, and nothing at runtime covers it

Legacy substitutes the `VillaConfigPropertyDefault` value at read time when
the `IsDefault*` flag is set **or** the stored value is ≤ 0
(`PropertyService2.cs:169-235`). CUTOVER deferred reproducing this "pending
confirmation that GAP-070's `PropertyDefaults` doesn't already cover it". It
does not: `PropertyFinance._policy()` falls to the frozen `_POLICY_FALLBACKS`
(deliberately not `PropertyDefaults`), and the engine reads `PropertySettings`
directly. Measured on the 291 live villa finance rows and 293 settings rows:

| Field | Loaded | Legacy effective | Rows wrong |
|---|---|---|---|
| Commission % | 0 | 20 | 69 (engine reads `effective_commission()` → owner net wrong) |
| Days balance due | 0 / 60 floor | 56 | 91 stored 0 → 0; 47 NULL → 60; only 152/291 match |
| Security deposit required | False | True, 10 %, 56 days | 46 |
| Min nights | 1 | 7 | 196 |
| Changeover day | Sunday | Any (`-1`) | 25 (`IsDefaultSettingChangeoverDayId=1`, stored 0) — CUTOVER's deferral list omits this one |
| Currency | NULL | EUR | 91 stored 0 (plus 97 more from §3) |

Prices-entered-as is correct (GROSS) only because the loader hardcodes it:
91 villas store `SettingPricesEnteredTypeId=10` (Net) but are all
IsDefault-flagged to the config's 20. Add a comment; a post-dump unflag would
mis-load silently.

### 3. The live EUR currency row never loads; the deleted one wins

`VillaCurrency` has EUR twice: Id 2 (`DeletedAt=2023-10-21`) and Id 3 (live,
`IsDefault=1`). The declarative query has no `ORDER BY`, keep-first sees Id 2,
and `lookups.py:75-77` skips Id 3. So `Currency(EUR).legacy_id="2"` and every
`filter(legacy_id="3")` misses. Id 3 is what the data references: 97 live
villas' `SettingCurrencyId`, 2 854 live rate rows, 21/23
`VillaQuotationDetails`, and `VillaConfigPropertyDefault.CurrencyId`.

- `PropertySettings.currency` NULL on **188/293** villas (139 active).
- **6 EUR seasons stamped GBP or USD** — `pricing.py:258-264` falls back to
  the villa's newest non-null rate-row currency when the plan's id misses.
- 21/23 quotation lines silently take the property-chain currency
  (`finance.py:420-423`); `BookingChargeItemLoader` would *raise* on the same
  id (`bookings.py:390-396`).
- `PropertyDefaults.currency` NULL.
- `lookups.py:81` `is_active = not bool(row.get("DeletedAt"))` is dead code:
  `DeletedAt` is not in the declarative field map, so it is never fetched.

### 4. Rate rows legacy could never quote load as priced bands, some at zero

Legacy quotes only rows with `WeeklyPrice > 0` **and** `NightlyPrice > 0`
(`vw_getRates`, `sp_getQuotationPrices`; `RatesModel.Price` returns
`WeeklyPrice` for non-extras, so the `Price` column is never a quote input).
The loader:

- (a) uses `Price` as the nightly figure when weekly and nightly are NULL
  (`pricing.py:482-484`) — a **weekly** number stored as nightly. 587 bands on
  the scratch DB, all past-dated on this dump.
- (b) treats `0.00` as a present price (`_row_prices` tests `is None`). **48
  future non-POA bands at nightly 0.00**, e.g. villa 463 Housemartin plan 693,
  26 Jul 2025 → 2 Jan 2026 at 0.00 (legacy `Price` 13 125 / 18 375).
  `rateband_has_price_or_poa` evidently accepts 0.

### 5. Three adjacent parity gaps (decided 2026-09-11)

- **Unapproved rates.** Legacy's quote procedure has no `IsApprove` filter;
  the engine prices `is_approved=True` only (`engine.py:623`). 352 unapproved
  future rows (22 %); 429 bands on the scratch DB will return
  `NoRateAvailable`. **Decision: load as approved**, keeping the legacy flag
  visible (notes/audit) so staff can see which were drafts.
- **Per-rate commission/tax.** Legacy `RatesModel.Calculate()` derives
  commission and tax from the **rate row**; the engine from `PropertyFinance`.
  `pricing.py:534-543` does not select `Commission/CommissionType/TaxRate/
  IsTaxExempt`. 327 future rows disagree with their villa's finance row (254
  at 0 % vs 20 %, 44 at 15 %, 16 at 17 %, 5 at 16.67 %, 4 fixed amounts on
  villas 59/245/416; villa 93 has 20 rows at 13 % tax vs a 0 % finance row).
  Guest price unaffected; owner-net reporting is. **Decision: reconcile per
  villa** — when the finance row is default/zero, set commission/tax from the
  majority of that villa's future rate rows and report the villas with mixed
  rates for a human call.
- **Season envelope.** `RatePlan.effective_from/to` come from
  `VillaSeasonDates` (`pricing.py:249-250`); the engine picks plans whose
  window covers the stay (`engine.py:594-597`); legacy ignores
  `VillaSeasonDates` for pricing. 268 priced live rows (89 future) sit
  outside their season's envelope; 64 loaded plans have periods outside their
  own window. **Not decided** — explore once the other loader questions have
  landed; the two options are widen-the-window-in-the-loader (min/max over
  both sources) or leave it to SPEC-001. Either way, filter
  `VillaSeasonDates.DeletedAt` in the MIN/MAX subselects (95 deleted rows; 0
  envelope changes on this dump).

## Proposed fix

1. **Type codes.** `{10: PERCENT, 20: FIXED}` in all three finance maps and
   the defaults loader; fix the fixtures. Treat `0` as "unset", not a map miss.
2. **IsDefault / ≤ 0 resolution.** Read the single `VillaConfigPropertyDefault`
   row once (the loader already has `PropertyDefaultsLoader`'s query) and
   apply the legacy rule in `_finance_defaults` and `_write_settings`: flag
   set **or** stored value ≤ 0 → config value. Cover commission, balance-due
   days, security deposit (required / type / amount / days — legacy takes
   sec-dep days from `DaysBalanceDueBeforeArrival`, not the CPD column), min
   nights, changeover day, currency. Record the per-field counts above in
   `DRYRUN_LOG.md` as the calibration evidence. This closes CUTOVER §4's
   deferral note and COVERAGE item 6's "KEEP until resolved".
3. **EUR row.** Order live rows first (`ORDER BY CASE WHEN DeletedAt IS NULL
   THEN 0 ELSE 1 END, Id`), and when a live row meets a code already claimed
   by a deleted twin, move `legacy_id` to the live row. Alternatively keep a
   `{legacy_id: code}` alias map consulted by every
   `Currency.objects.filter(legacy_id=…)` call (six call sites:
   `properties.py:195`, `finance.py:421`, `defaults.py:153`, `bookings.py:80,
   390`, `pricing.py:258`). Either way delete or implement the dead
   `is_active` line.
4. **Zero-priced bands.** Mirror legacy in `_row_prices`: a band needs a
   positive weekly or nightly figure; drop the Price-as-nightly branch and
   the test that pins it; treat `0.00` as absent. The skipped rows join the
   `VillaSeasonRate` expected-loss itemisation in `reconcile_legacy.py`.
5. **Approved / commission / envelope** per §5.
6. **Value invariants in `reconcile_legacy`** (the only kind of check that
   protects these paths — every defect above passed the count checks):
   zero `PropertyFinance` rows with a NULL calculation type; zero active
   villas with NULL `PropertySettings.currency`; the EUR row's `legacy_id`
   equals the live legacy id; zero imported non-POA bands at 0.00; zero
   imported plans with a period outside their own window (once §5 is
   settled). Legacy side is a constant `SELECT 0`, same pattern as the
   SMELL-021 non-GROSS check.

## Acceptance

- Transform tests on dict fixtures using codes 10/20 and the real CPD row
  shape (style: `data_migration/tests/test_country_loader.py`).
- Live dry-run on the dump: `PropertyFinance` calculation types non-NULL on
  291/291; commission 20 % on the 69 flagged villas; sec-dep percent on the
  49; `PropertySettings.currency` non-NULL on 293/293, min nights 7 on the
  196, changeover ANY on the 25; `Currency(EUR).legacy_id == "3"`; 0 EUR
  seasons stamped GBP/USD; 0 non-POA bands at 0.00; 0 unapproved imported
  bands.
- The new `reconcile_legacy` value invariants are green and the
  `VillaSeasonRate` gap is recalibrated with the dropped zero/priceless rows
  itemised.
- CUTOVER §4 deferral note replaced by the as-built rule; `DRYRUN_LOG.md`
  carries the per-field counts; `design/decisions.md` records the approved-
  rates and per-villa-commission decisions.
- Quality gate green.

## Dependencies

- **Blocks cutover.** Nothing else in the loader is worth re-running until
  this lands; BUG-029's two-run idempotency test should be built against
  this ticket's output.
- **GAP-107 §1/§3**: extras and the 1236 pin are independent; GAP-108 pins
  the reconcile constants.
- **SPEC-001**: owns the season-envelope question if it is not settled here.
- **GAP-070 / GAP-073**: the deferral this ticket closes.
- **SMELL-021** (done): its "legacy has no NET/GROSS signal" rationale is
  wrong (`RatesModel.Calculate()` branches on `PriceType`; 1 931 live rows are
  Net) though the GROSS stamp remains the right outcome — corrected in the
  GAP-108 docs pass, not here.
