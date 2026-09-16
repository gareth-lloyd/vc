# GAP-115 — `VillaFinance.SecurityDepositPaymentMethod`: three integer codes nobody can decode

- **Severity:** 🟢 Gap (cutover fidelity, low blast radius). The column is
  effectively constant on real data, so dropping it costs almost nothing —
  but it is being dropped by *omission*, which is what this ticket fixes.
- **Source:** GAP-108 dry run, ResProd (13-Aug-2026), measured 2026-09-16.
  One of the new columns the ResProd schema added since the 24-Apr-2025 dump.
- **Files touched:** `data_migration/loaders/finance.py` (only if the answer
  is "home it"); `COVERAGE.md` / `CUTOVER.md` §5 expected-loss list;
  `todo/gap-109-legacy-loader-silent-column-drops.md` row 9, which covers the
  column's neighbours.

## The facts

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

## The decision this ticket exists to force

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

## Acceptance

- The meaning of 0 / 10 / 20 is recorded in `design/decisions.md` (or
  recorded as "asked, no answer available" — an explicit unknown beats a
  silent drop).
- The column is either loaded with a test, or named in `CUTOVER.md` §5's
  expected-loss list with its distribution.
- `COVERAGE.md` stops listing the column as unclassified.

## Dependencies

- **GAP-109** row 9 already covers the neighbouring `VillaFinance` drops
  (`SecurityDepositCalculateFromId`, `IsManualUpdate`, `SeasonId`,
  `BankAccCounty`). Fold this in when GAP-109 is picked up if the timing
  suits — it is the same conversation with the same person.
