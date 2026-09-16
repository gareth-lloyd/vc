# GAP-112 — Post-load pass to relink enquiry-born quotations to the person the sheet import later mints

- **Severity:** 🟡 Gap (cutover fidelity, customer-facing). 321 loaded
  quotations sit on the unknown-client sentinel even though the customer's
  name and e-mail are right there on the linked enquiry, and for 290 of them a
  `Person` carrying that e-mail exists in the same database by the end of the
  run — just not yet when the quotation was loaded.
- **Source:** GAP-108 Unit 8b/8d, ResProd dry run 2026-09-15/16
  (`data_migration/DRYRUN_LOG.md` run 5). Deliberately **rejected for
  GAP-108** — see "Why not in GAP-108".
- **Files touched:** a new post-import management command (or a documented
  step inside `import_enquiry_sheet`); `data_migration/loaders/reservations.py`
  (`EnquiryLoader`, `QuotationLoader`); `data_migration/CUTOVER.md` §4d and
  the §5 gap table; a reconcile check.

## The problem

`EnquiryLoader` resolves an enquiry's `Person` with a strict matcher — an
**active** `match_person_by_email` hit, name agreeing. At the moment the
enquiry rows load, the people who would match do not exist yet: they are
minted **later in the same cutover** by `import_enquiry_sheet`, as
`sheet-person-*`. So `Enquiry.person` is left NULL, and `QuotationLoader`'s
enquiry hop (GAP-108 U8b) then has nothing to hop to and falls back to the
unknown-client sentinel.

The ordering is not accidental and is not worth inverting: the sheet is a
separate, human-curated source that legitimately arrives after the legacy
tables.

Measured on the run-5 database, over the **321** sentinel-client quotations
(every one of which has a named, live enquiry):

| Outcome once the sheet import has run | Quotations |
|---|---|
| E-mail matches exactly one loaded `Person`, names agree — the strict matcher would now succeed | 268 |
| E-mail matches a loaded `Person` but the **names disagree** | 11 |
| E-mail is **shared** by more than one loaded `Person` | 11 |
| E-mail matches nobody | 30 |
| Enquiry carries no e-mail at all | 1 |
| **Total** | **321** |

So 268 are unambiguous, 22 are ambiguous, and 31 are genuinely unresolvable.

## Proposed fix

A post-sheet-import pass (own command, so it is re-runnable and auditable)
that walks enquiries with `person IS NULL` and a non-blank e-mail, re-runs the
**same strict matcher** the loader uses, and on a unique active hit sets
`Enquiry.person` and re-points any quotation still on the sentinel.

Non-negotiables:

- **Leave the ambiguous cases alone.** Shared e-mail (11) and name-disagree
  (11) rows stay on the sentinel and are *reported*, not guessed. A shared
  `info@` address genuinely belongs to several real people — the same caveat
  CUTOVER §6g records for the merge candidates.
- Reuse the loader's matcher rather than reimplementing it; if the matcher
  changes, both paths must move together.
- Write an `AuditLog` trail for each relink (the row's customer changes).
- The pass must be idempotent, and a no-op on a database where it has already
  run.

## Acceptance

- The command relinks the 268 unambiguous quotations and reports the 22
  ambiguous + 31 unresolvable ones by category, matching the table above on a
  fresh ResProd load (re-derive the counts on the run of the day; do not
  hard-code these).
- Ambiguous rows are provably untouched.
- A reconcile check pins the residual sentinel count, so a future run cannot
  silently regress to 321.
- `CUTOVER.md` §4d describes the step in the cutover order (after both sheet
  imports), and the §5 client-gap derivation is updated to reflect it.

## Why not in GAP-108

The alternative considered was minting a `Person` per enquiry inside
`loadlegacy`. Rejected: it would create roughly 2 700 enquiry-born people,
duplicating the ones the sheet import is about to create properly, and it
would move every `Person`/`PersonEmail` count GAP-108 Unit 8 had just pinned.
Relinking after the fact is strictly smaller and reversible.

## Dependencies

- Runs **after** `import_enquiry_sheet` (and harmlessly after
  `import_past_bookers`), so it belongs in the cutover order, not in
  `loadlegacy --all`.
- GAP-108 U8b/U8d supply the enquiry hop and the sentinel-bounded borrow rule
  this pass builds on.
