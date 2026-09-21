# Legacy → Postgres Cutover Playbook

This is the ops checklist for the final cutover from `ResSystem/` (.NET 7 +
Azure SQL Edge) to the new Django REST API + Postgres backend.

Run end-to-end **after** a green CI on `main` and a confirmed dry run
against a recent dump. The goal is to land every legacy row that has a
schema home in the new system, with zero unexplained gaps in
`reconcile_legacy`.

Companion documents: `ACCEPTANCE.md` defines what "the migration succeeded"
means (the S1–S7 standards and the verdict procedure this runbook feeds);
`COVERAGE.md` classifies every table in the live dump (loaded / joined /
dropped-with-justification); `DRYRUN_LOG.md` records dry-run results and
calibration evidence.

## 0. Prerequisites

- A read-only Azure SQL Edge container holding the latest production dump
  (the `res-db` service in `ResSystem/docker-compose.yml`).
- The Villa Collective Postgres DB at the target URL — empty, freshly
  migrated. `loadlegacy --all` enforces this: it is a **one-shot** (BUG-029)
  and refuses, before writing anything, a DB whose `Country`, `Currency` or
  `Property` already carries a legacy `legacy_id`.
- A staff user authorised to run management commands on the production
  cluster.
- `LEGACY_DATABASE_URL=mssql://sa:<pw>@<host>:<port>/ResProd`
  exported in the shell (the database name is whatever
  [§3](#3-reseed-res-db-from-the-final-dump) restored into; `ResProd` is the
  convention).
- **A dump on the current legacy schema.** GAP-108 retargeted every loader and
  every reconcile query at `ResProd` (13-Aug-2026 production), which has drifted
  from the older `NewResSystem` snapshots: 73 tables (12 new), `DeletedAt` on
  `VillaEnquire`, and `IsActive` soft-delete columns on `VillaRooms`,
  `VillaFeaturesMappings`, `VillaCollectionsMappings` and `VillaNearBy` that the
  loaders now honour. The 24-Apr-2025 `NewResSystem` schema is **no longer a
  supported source** — loaders will fail or silently over-count against it.
  A dump newer than 13-Aug-2026 is expected and fine; the expected gaps in
  [§5](#5-verify-with-reconcile_legacy) were pinned on that date and move with
  the data, so re-derive any that shift rather than nudging the numbers.

## 1. Freeze legacy writes

Per ops procedure — typically by switching the legacy app to maintenance
mode. There is no delta mode: a legacy write that lands after the freeze
means a fresh reload from a newer dump (see [§6](#6-late-writes)).

## 2. Take the final legacy dump

The current convention is a SQL Server backup, `NewResSystem_YYYYMonDD.bak`
(e.g. `NewResSystem_2026Aug13.bak`) — that is how every production dump has
arrived since 2026-08. The older `live-db-YYYY-MM-DD.sql` convention (a
UTF-16 LE T-SQL script) is still restorable but carries the retired schema
([§0](#0-prerequisites)).

The file can live anywhere readable; `ResSystem/` is the usual home and is
gitignored, so it exists only in the main checkout.

## 3. Reseed `res-db` from the final dump

```bash
.claude-tmp/drop-and-reseed.sh <dump-file> [db-name]     # db-name: ResProd
```

The script takes the dump path and the target database, so it runs from the
main checkout or any worktree. A `.bak` is copied into the container and
restored with `RESTORE … WITH MOVE` (the backup carries the original server's
file paths, so every logical file is moved onto this container's data dir under
the target name); a `.sql` is transcoded from UTF-16 only if it actually carries
that BOM, then piped through `sqlcmd`. The target database is **dropped** if it
exists — name it deliberately.

It finishes by printing the `VillaMaster` row count. Expect **545** on the
13-Aug-2026 dump; a newer one should be in the same region. A wildly different
number (or a failure to reach this line) means the restore did not land — stop
here rather than loading a half-restored database.

## 4. Run every loader

> **Pre-step for any DB that already holds rate plans (GAP-110, `pricing/0011`).**
> `0011` adds `rateplan_one_active_per_regime` (one *active* `RatePlan` per
> `(property, currency, price_basis)`). Its `RunPython` step retires only
> **loader** rows (pre-regroup season-keyed `legacy_id`s); the `AddConstraint`
> then **hard-fails** on any two hand-built active plans in one regime, and
> `migrate` stops there. Check first:
>
> ```python
> # uv run python manage.py shell
> from django.db.models import Count
> from pricing.models import RatePlan
> RatePlan.objects.filter(is_active=True).values(
>     "property_id", "currency_id", "price_basis"
> ).annotate(n=Count("id")).filter(n__gt=1)
> ```
>
> (SQL: `SELECT property_id, currency_id, price_basis, count(*) FROM
> pricing_rateplan WHERE is_active GROUP BY 1, 2, 3 HAVING count(*) > 1;`.)
> Remedy: deactivate the extras by hand (keep the one whose periods should
> price; a retired plan's periods still own their dates — see §5 item 6),
> then run `migrate`. A fresh DB has nothing to check. _(Historical — in-place
> only; the one-shot cutover always loads a fresh DB.)_

```bash
uv run python manage.py migrate           # applies pending schema migrations
uv run python manage.py loadlegacy --all
```

> **Migration graph flattened (2026-07-08).** The ~150 incremental migrations
> were collapsed to a fresh `0001_initial` per app (plus a handful of hand-kept
> extension/sequence/EXCLUDE/seed migrations). This is transparent to the
> `migrate`-then-`loadlegacy` fresh-rebuild path documented here — the resulting
> schema is byte-identical. Only the historical **in-place-upgrade** paths that
> referenced specific old migration numbers (`reservations/0035`,
> `accounts/0012`) are gone; those were never needed for a fresh cutover.
>
> **`VillaPropertyCategory` is no longer loaded (GAP-093, 2026-09-01).**
> `Property.category` and the `PropertyCategory` lookup were removed; the
> table is classified as dropped in `COVERAGE.md`.

Expect **~7 minutes** on the live snapshot (GAP-108 dry runs on ResProd:
416.9s, 6m16s and 6m56s across three clean loads of the 13-Aug-2026 data — the
"~2 minutes" quoted here before GAP-108 was the much smaller 24-Apr-2025 dump).
All **31** registered loaders must report `0` in the `errors` column of the
per-loader summary; investigate any non-zero before proceeding. Since 2026-07-05 the command is strict and crash-isolated: a
loader that raises no longer aborts the run (its failure lands in the
summary as `<loader crashed>`, remaining loaders still run, the sequence
sync still happens — a failing sync is reported as a
`sync_quotation_sequence` summary row) and the command **exits non-zero if
any loader crashed or reported errors** — so "step passes iff exit 0" now holds here too.

Two loader behaviours to know about (both 2026-07-05, see `DRYRUN_LOG.md`):

- **Legacy `IsDefault*` / zero-value resolution is ported (BUG-028,
  2026-09-14; dry run 4).** The loaders read the single
  `VillaConfigPropertyDefault` (CPD) row from legacy at load time — never the
  operator-editable `PropertyDefaults` singleton — and fail the loader if it
  is missing. As built:
  - **Type codes** are `10 = percent`, `20 = fixed`; `0`/NULL is unset.
  - **Finance** (`PropertyService2.cs:169-238`): a set `IsDefaultCommission`
    / `IsDefaultPaysched` / `IsDefaultSecDep` flag copies that whole block from
    the CPD; otherwise each numeric `<= 0` (NULL included) takes the CPD value
    and booleans stay the row's own (NULL = False). Security-deposit days due
    come from CPD `DaysBalanceDueBeforeArrival` (legacy's own choice). The
    commission *type* also fills when blank — a deliberate deviation, so a CPD
    20 never pairs with a template's FIXED. The GAP-070 owner template merge
    runs afterwards and only fills what the CPD never covers (bank, tax,
    notes). A villa with no `VillaFinance` row resolves the same way from its
    owner template, or from an empty row when it has none.
  - **Per-villa commission / tax (D7):** before the CPD rule, the majority
    of the villa's priced non-POA rate rows ending on or after
    `reference_date` (the load day; ties → lowest type, then amount) replaces
    the villa's own commission and tax — legacy's quote reads the rate row
    first (`quote_price_calc-query.sql:96-146`). Only positive commissions and
    positive / exempt taxes vote; a villa without a majority keeps its own.
    Villas whose rows disagree are logged (`finance_rate_rows_mixed`) for a
    human call.
  - **Settings** (`:668-686`) are flag-only: a set `IsDefaultSetting*` flag
    takes the CPD currency, changeover day, min nights, check-in/out and
    pre-approval; unflagged values load as stored. `prices_entered_as` stays
    GROSS.
  - **Currencies:** deleted `VillaCurrency` rows load retired; a live row
    claims its code from a deleted twin, so EUR resolves to legacy Id 3.
  - **Rate bands:** only `NightlyPrice` / `WeeklyPrice > 0` (or `IsPOA`) are
    prices — `Price` and `0.00` never are. Every imported band loads approved;
    a legacy-unapproved row keeps its precedence and gets
    `Unapproved in legacy (IsApprove=0)` appended to `notes` (a carried-forward
    band copies that note — clear it on review).
  - In-place re-runs are **unsupported** (one-shot, BUG-029) — `loadlegacy
    --all` refuses an already-loaded DB; drop, recreate and reload instead.
- **`availability_block`** ports future non-available legacy calendar runs
  into `BookingHold(reason=MANUAL)` rows (see the reconcile table below) and
  full-replaces its own `avail-*` slice per run. Duplicate `(villa, day)`
  rows are first deduped to the **latest edit** by
  `(COALESCE(UpdatedAt, CreatedAt), Id)` — legacy updates rows in place, so
  `Id` alone is not recency — and only then filtered to the blocking statuses
  30/40/50/60, so a newer release (status 70) supersedes an older block.
  Each hold is written under its own savepoint (error id
  `avail-<villa>-<start>`), so one bad row is reported without aborting the
  rest; `syncrecord_zoho` does the same per row (error id `<table>:<Id>`).

> **SUPERSEDED 2026-07-29 (import pivot — GAP-089):** the GAP-082 note that
> stood here required one FULL booking load (`loadlegacy booking`) before the production `zoho_backfill --kinds booking`, because
> `BookingLoader` back-stamps `Booking.created_at` from legacy `CreatedAt`
> (the Zoho payload's `booking_date`, the CRM's historic-import filter).
> Per the 2026-07-29 Limitless call, historic bookings now arrive via the
> **spreadsheet import** instead — the legacy booking-loader step is no
> longer part of cutover (the loader code stays as the schema record).
>
> **Built 2026-09-02 (GAP-089).** The sheets carry a villa, a year and a
> legacy booking number per stay — no dates, no money — so they land as
> `reservations.PastStay` rows (Customer-360 "Past stays", repeat-customer
> flag), **not** as Bookings, and are **not** pushed to Zoho (deferred —
> raise the shape with Limitless). The two commands run right after
> `loadlegacy --all` and before `reconcile_legacy`
> (`D` = wherever the two `.xlsx` files live; they are not in the repo):
>
> ```bash
> ./manage.py import_enquiry_sheet --file "$D/Enquiries - FINAL.xlsx" --dry-run
> ./manage.py import_enquiry_sheet --file "$D/Enquiries - FINAL.xlsx"
> ./manage.py import_past_bookers  --file "$D/VC Past Bookers Final.xlsx" --dry-run
> ./manage.py import_past_bookers  --file "$D/VC Past Bookers Final.xlsx"
> ./manage.py relink_enquiry_customers --dry-run   # GAP-112, see below
> ./manage.py relink_enquiry_customers
> ./manage.py import_archive_stays --dry-run       # GAP-113, see below
> ./manage.py import_archive_stays
> ./manage.py relink_enquiry_customers --mint-unmatched --dry-run
> ./manage.py relink_enquiry_customers --mint-unmatched   # again — see below
> ```
>
> **`--mint-unmatched` goes on the SECOND run only** (GAP-118 §3). It mints
> one customer `Person` per enquiry address no loaded person holds
> (`enquiry-person-<sha1(address)>`, 543 enquiries and 51 stranded
> quotations on the 2026-09-18 dev DB), names it from the lowest-id enquiry
> in the group that carries a name — `(anon)` is dropped per field, and a
> wholly anonymous group takes the address as its first name, the
> `find_or_create_person` rule that keeps it off "Client #id" — takes the
> phone from the lowest-id enquiry that has one (independently of the name:
> nothing re-adds a dropped number, both sheet importers guard on
> `not phones.exists()`), and links every enquiry sharing that address. Two
> different names on one address mint ONE person and the name not taken is
> reported as `name not used (address carries several)`. On the **first** run it would mint people `import_archive_stays`
> is about to mint properly — the duplication GAP-112's "Why not in GAP-108"
> rejected — so the flag is opt-in and belongs after the archive stays. The
> ambiguous categories are never minted: `shared_email`, `names_disagree`,
> `no_email` and `inactive` stay on the sentinel exactly as GAP-112 left
> them. Idempotent: the key is derived from the address, so a third run
> mints nothing.
>
> **`relink_enquiry_customers` runs twice, and the second run is not
> optional** (run 8, 2026-09-18). `import_archive_stays` mints people of its
> own — 7 on the reference load — and some of them are the holder of an
> e-mail that a still-sentinel enquiry was waiting for, so they make a handful
> of enquiries relinkable that were not when the first relink ran. Skip the
> second run and `reconcile_legacy` blocks on the GAP-112 invariant: run 8 saw
> `Quotation on unknown client with a relinkable enquiry` = **2**, and the
> second relink moved exactly those 2 quotations and 3 enquiries, after which
> the gate passed. The command is idempotent, so a second run costs nothing
> when the archive import unlocked nothing.
>
> Each prints created / updated / skipped-per-reason counts plus the villa
> and person names it could not resolve (left unlinked or skipped —
> reported, never guessed); `--dry-run` rolls the whole run back. Both are
> re-runnable: people are found by `sheet-person-…` key (blank-fill only,
> so operator edits survive), stays and enquiries are create-only on their
> `sheet-stay-…` / `sheet-enquiry-…` keys. Two re-run caveats: a person
> staff **merged away** loses the `sheet-person-…` key with the deleted
> row, so a later re-run can re-mint that person's shell (stays/enquiries
> stay on the merge target); and a person staff **anonymised** has no
> name/e-mail left to match, so a later re-run re-creates them from the
> sheet — redact the sheet row too before re-running after an erasure
> (a merely deactivated person is recognised and skipped). Sheet enquiries land
> `DEAD / lost_reason=UNKNOWN / COLD` with `created_at` back-stamped to the
> sheet date (the res `EnquiryLoader` back-stamps its rows from legacy
> `CreatedAt` for the same reason — historically one FULL `loadlegacy enquiry`
> run repaired rows loaded before 2026-09-02; a fresh one-shot load never needs it).
> The res `EnquiryLoader` parks its own stale leads the same way (BUG-030
> §21): a `VillaEnquire` row created more than `STALE_ENQUIRY_DAYS` (90,
> `data_migration/sheets/constants.py`) before the dump's newest enquiry,
> with no live quotation, loads `DEAD / UNKNOWN / COLD`; the loader logs
> the cutoff and the count (`data_migration.enquiry_stale_cutoff`). A legacy
> enquiry with `Adult` 0 or NULL (54 in the reference dump) loads `adults=0`
> rather than a made-up 2 (BUG-030 §23): the enquiry form and the quote
> search require at least one adult, so staff set the party size before
> editing or quoting such an enquiry. `reconcile_legacy` leaves
> every `sheet-` row out of its counts. The later `zoho_backfill` contact
> and enquiry kinds push the sheet people (with their tags — including the
> new `hnw` / `owner` values) and the ~2.4k DEAD historic enquiries by
> design; the booking kind is unaffected.
>
> **Then relink the enquiries the sheet people belong to (GAP-112).**
> `EnquiryLoader` links an enquiry to a customer only on a strict e-mail +
> name match, and the people it would match are minted *later*, by the sheet
> imports — so those enquiries load customer-less and their quotations fall to
> the unknown-client sentinel ([§4d](#4d-customers-load-straight-to-person-gap-045)).
> `relink_enquiry_customers` re-asks the loader's question once both sheets are
> in, and must run **after `import_past_bookers`, again after
> `import_archive_stays`, and before `reconcile_legacy`
> and any `zoho_backfill --kinds enquiry`** (a relinked enquiry pushed before
> it would reach Zoho without its contact). It prints, per category, how many
> enquiries and quotations it relinked or left alone, plus the guest
> preferences that followed their quotation; `--dry-run` rolls back. It is
> re-runnable — a second run relinks nothing unless something has since minted
> the person an enquiry was waiting for, which is exactly why
> `import_archive_stays` is followed by another run — and never touches an enquiry
> without a legacy `legacy_id` (a sheet or post-go-live one). On the run-5
> database (13-Aug-2026 `ResProd` + both sheets) it gave, over the 321
> sentinel quotations — re-derive these on the day, don't compare to them:
>
> | Outcome | Quotations | Enquiries |
> |---|---|---|
> | `relinked` — one person holds the address, names agree | 268 | 606 |
> | `shared_email` — more than one person holds it: left for a human | 11 | 25 |
> | `names_disagree` — the one holder's name differs: left for a human | 11 | 39 |
> | `inactive` — the one holder is deactivated: left alone | 0 | 0 |
> | `unmatched` — nobody holds the address | 30 | 482 |
> | `no_email` | 1 | 3 |
>
> plus **16** sentinel guest preferences moved with their quotation.
>
> **GAP-118 §3 — the second run also mints.** `--mint-unmatched` clears the
> `unmatched` bucket (an address no `Person` holds at all): one customer per
> distinct address, its enquiries linked and their sentinel quotations
> followed in the same pass, so the GAP-112 invariant stays 0. The minted
> rows carry the `enquiry-person-` prefix, which `reconcile_legacy` excludes
> from the `Person (owner/agent)` slice (they have no VillaContact twin) and
> `channels_writable` admits (a later sheet import may add their phone). What
> is left on the sentinel afterwards is only the ambiguous residue, reported
> and never guessed — see the §5 note below.
>
> **Then date the past stays from `VillaArchiveBookings` (GAP-113).** Between
> Dec-2025 and Mar-2026 staff re-keyed sheet stays into legacy with exact
> dates, amount, currency and the lead guest's contact details.
> `import_archive_stays` runs **after `relink_enquiry_customers`, and is
> itself followed by a second `relink_enquiry_customers` (the people it mints
> unlock a few more enquiries), before `reconcile_legacy`**. It reads the live
> rows, folds re-saves of one stay
> into a single stay (same villa, overlapping dates, same `BN…` number, or
> else the same e-mail or surname), and matches each stay against the
> `sheet-stay-…` rows:
>
> - **enrich** — one sheet stay matches (same year, by booking number, else
>   by the one customer holding the e-mail, else by exact first + last
>   name, at the same villa or an unlinked one). Its empty dates, amount
>   and currency are filled and the archive notes are appended as a line.
>   Its person and `property` are never touched.
> - **create** — nothing matches. A `PastStay` keyed `archive-stay-<Id>`
>   (the highest `Id` among the re-saves) lands on the e-mail's one active
>   customer, or else on `find_or_create_person` with the archive name and
>   address. The mobile is added only to a person with no phone whose
>   channels the sheets own.
> - **skipped, with ids** — `bn_year_conflict` (the booking number is on a
>   sheet stay in another year), `weak_conflict` (the only name or e-mail
>   match is at another villa), `ambiguous`, `target_taken` (the sheet stay
>   already carries different dates or money), `target_contested` (two
>   archive stays claim one sheet stay), `person_ambiguous` /
>   `person_inactive`, and `exists` (nothing left to land; counted, not
>   listed).
> - **flags, with ids** — `dates_dropped` (no `ToDate`, `ToDate` not after
>   `FromDate`, or more than 45 nights: the stay lands with its year only),
>   `duplicate_conflict` (re-saves disagree on amount, currency, dates or
>   booking number; the highest `Id` wins, except that the booking number
>   and e-mail come from the latest re-save that has one), `property_differs` (the archive's villa differs from
>   the enriched sheet stay's; the sheet's is kept).
>
> Amount is stored as recorded; `CurrencyId 0` leaves the currency empty
> (the Customer-360 row shows a plain number) and `Amount 0` stores none.
> Party size, `ZohoId` (GAP-098) and the free-text contact fields of
> *enriched* stays are not imported. Row Id 297 is a staff test row and is
> always skipped. One transaction, a savepoint per stay, no Zoho pushes;
> `--dry-run` rolls back, and a second run writes nothing (every landed stay
> is `exists`; the skips repeat). On the run-6 database (the run-5 load of 13-Aug-2026 `ResProd`
> plus both sheets; 272 live rows, 253 stays) it gave — re-derive on the day:
>
> | Outcome | Stays | Ids |
> |---|---|---|
> | `past_stay` updated (enrich) | 220 | |
> | `past_stay` created | 27 | incl. future stay 5 |
> | `bn_year_conflict` | 4 | 57/94, 110, 117, 201 |
> | `weak_conflict` | 1 | 53 |
> | `exists` | 1 | 290 (dates dropped, nothing else to fill; counted only, the report names it under `dates_dropped`) |
> | `test_row` | 1 row | 297 |
>
> plus 7 persons created, 1 blank-filled and 21 phones added; flags
> `dates_dropped` 28, 61, 76, 233, 290; `duplicate_conflict` 57/94, 268/280;
> `property_differs` 97. The six stays still running or ahead of cutover
> (5, 40, 46, 227/234, 278, 279) all land; their nights are already blocked
> by `availability_block` holds, and none becomes a `Booking`.

## 4a. Pricing summaries — automatic, with a manual fallback

`VillaPricingSummary` (the display min/max price and party shown on property
cards) is normally maintained by a Celery task that `pricing.signals` enqueues
on every `RatePlan` / `RateBand` write. A full load writes hundreds of
thousands of those, so **`BaseLoader.load()` suppresses the enqueue** for the
whole run — the same mechanism that already suppresses the Zoho push
(`suppress_summary_rebuild`, beside `suppress_zoho_push`).

**`loadlegacy` rebuilds them itself**, in one synchronous pass after the
loaders and the sequence sync, and prints

```text
Rebuilt 359 pricing summaries.
```

as the last line before the per-loader summary table — **359** on the
13-Aug-2026 dump. So there is nothing extra to run here in the normal case;
this section is what to check and how to recover.

The rebuild is crash-isolated like a loader: if it raises, the run does **not**
abort, a `rebuild_summaries` row appears in the summary table carrying
`<rebuild crashed>`, and `loadlegacy` exits non-zero. That is the one case
where the property cards would come up blank, and the fix is the manual
equivalent:

```bash
uv run python manage.py rebuild_summaries     # idempotent; safe any time
```

It walks every distinct `(property, currency)` owning a rate plan, recomputes
each synchronously, takes seconds, and prints the same count. Re-run it freely
— after a hand-edit to rate plans, or simply to confirm the number.

**No Celery worker is needed for the cutover.** Loader pushes are suppressed
and the rebuild is synchronous, so the `celery` list should read **0 before
and after** the load (`redis-cli LLEN celery`). A non-zero tail means something
enqueued work the cutover did not expect — find it before starting the worker,
because a worker draining stale messages against a freshly loaded DB is how a
dry run gets silently mutated.

**AuditLog volume.** The load writes one audit row per tracked-model save:
**72 009** rows on ResProd, dominated by `propertyimage` (18 232),
`propertyfeature` (13 359), `quotationline` (7 556), `rateband` (6 633),
`person` (6 252), `rateperiod` (6 222) and `enquiry` (5 081). That is expected,
not a leak — but it is the bulk of the load's write volume, so size the
transaction log and any audit retention policy for it.

**`PropertyFinanceLoader.reference_date` is the load day.** The per-villa
commission/tax vote (BUG-028 D7) counts only rate rows ending on or after that
date, so loading and reconciling on different days can shift which rows vote.
Run the whole sequence in one sitting — the `VillaAvailability` check has the
same "both sides move with today" property.

## 4b. Capture external IDs into `SyncRecord` (Zoho)

This step **captures** the external ids Zoho already issued against legacy
rows into `integrations.SyncRecord`, while the legacy DB is still readable.
The `syncrecord_zoho` loader runs as part of `loadlegacy --all` in step 4,
so there is nothing extra to run here — this step is the verification.

> **Live-schema reality (re-measured on ResProd, 13-Aug-2026 — GAP-108).**
> **Four** source tables are probed, not five. `VillaBooking` is off the list:
> GAP-089 unregistered the booking loader, so no loaded row exists for a
> booking `SyncRecord` to attach to. And `VillaQuotationMaster` **does** now
> carry a `ZohoId` — the 2026-07-05 note that stood here, saying it did not,
> was true of the 24-Apr-2025 dump only. The loader and this section still
> probe `INFORMATION_SCHEMA` per table and skip/annotate an absent column, so a
> schema-vintage difference cannot crash the run.
>
> | source | legacy ext id | loaded | sync records | expected gap |
> |--------|---------------|--------|--------------|--------------|
> | `VillaMaster.ZohoId` | 112 | 76 | 75 | **1** |
> | `VillaContact.ZohoId` | 0 | 0 | 0 | 0 |
> | `VillaEnquire.ZohoId` | 2 228 | 2 228 | 2 227 | **1** |
> | `VillaQuotationMaster.ZohoId` | 1 601 | 1 467 | 1 467 | 0 |
>
> **`VillaContact` carries the column but every value is blank** — contacts
> were never pushed to Zoho. Not a failure, but it means contact continuity is
> a non-issue at cutover: every contact will be a fresh insert on first push.
>
> Both expected gaps are the **same accepted shape** — two distinct legacy rows
> sharing one `ZohoId`, a source-side error in Zoho rather than duplicate
> records here. Both rows migrate; only one can hold the external-ID link, and
> the loader attaches it to the lower legacy Id (forced by `ORDER BY Id`, so it
> is reproducible) and logs `data_migration.zoho_id_duplicate`:
>
> - `VillaMaster` 88 (*Temenos Villa Templos*) and 339 (*Temenos Villa Kioni*)
>   share `577032000002128026`. **Product decision 2026-07-06: ACCEPT** — no
>   property merge is warranted.
> - `VillaEnquire` 1267 and 1268 share `577032000009062002` (found on the
>   GAP-108 dry run; same acceptance).
>
> Each gap stays **1** until the CRM source is corrected.

Why it is time-critical even though nothing syncs yet: the legacy DB is the
only home of these ids and it is decommissioned 24–48h after cutover (step
10). These ids are the routing keys for every future push — when outbound
sync goes live (deferred to v1.1; the engine in `integrations/tasks.py` is
`NotImplementedError` today, so **no push fires at the M1 cutover**), a
missing id makes Zoho INSERT a new record instead of UPDATE, orphaning years
of CRM activity. Capture them now or lose them. See
`django_res_design/design/backend/08-integrations.md` → "Migrating legacy external IDs".

Verify continuity:

```bash
uv run python manage.py reconcile_legacy --integrations
```

The `--integrations` flag adds, after the main table:

- **Zoho external-ID continuity** (enforced): per source table
  (`VillaMaster`, `VillaContact`, `VillaEnquire`, `VillaQuotationMaster`),
  the count of backfilled `SyncRecord(provider=ZOHO_CRM)` rows
  (with a non-blank `external_id`) vs the number of **loaded** rows that carried
  a legacy `ZohoId` — i.e. legacy rows whose `ZohoId` is non-blank *and* whose
  `legacy_id` resolves to an imported Django row. The raw legacy `ZohoId` count
  is shown alongside (`legacy ext id`) so you can see how many were not imported,
  but the gap is computed against `loaded`: a `ZohoId` on a row the loaders
  intentionally dropped (soft-deleted, empty `Name`, unresolvable FK) has no push
  target, so it is *not* a continuity failure and does not block. A non-zero gap
  is a **blocker** (the command exits non-zero): a loaded row whose `ZohoId` has
  no `SyncRecord` would duplicate on first push. Cutover must not proceed until
  the gap is zero, or the operator records it as an accepted loss with a written
  justification. (The check compares counts, not values; the one-shot
  `loadlegacy --all` writes every `external_id` from the final dump.)
- **WordPress surface** (informational only): legacy `VillaBooking.BookingUrl`
  (251 non-blank on ResProd) and `VillaSyncDetails` volume (5 773 rows over 2
  distinct `SiteId`s). Note the **plural** table name: the singular
  `VillaSyncDetail` this section probed before GAP-108 exists in no dump, so
  the row silently reported `n/a`. The WordPress backfill is **not built yet** —
  multi-site fan-out needs a `provider_instance` field on `SyncRecord` that
  the model doesn't have. This row reports the surface so it isn't silently
  treated as "all clear"; it never blocks. If WP continuity matters for this
  cutover, that model change and a `SyncRecordWordPressLoader` must land
  first — see `data_migration/WORDPRESS_BACKFILL.md` for the data-shape
  queries to run during this dry-run and the build-vs-descope decision.

Note: there is **no "disable outbound push" step at M1** — there is no push
engine to disable yet. Re-introduce a stop-the-bleeding posture (pause beat,
`SyncRecord.status=DISABLED`) in the v1.1 cutover checklist when `push_*` /
`reconcile_*` actually exist.

## 4c. Quotation-number high-water mark (automatic)

The loaders set `Quotation.number` explicitly from the legacy `QuotationNo`
(so `QVC{number}` / `VC{number}` references keep their exact legacy digits).
Setting the column directly does **not** advance the `quotation_number_seq`
sequence, so the first organically-created quotation after cutover would
otherwise draw a low `nextval` that collides with an already-imported
`QVC2`/`QVC3`/…

`loadlegacy` now fast-forwards the sequence past the highest imported number
automatically at the end of the run (it prints
`Quotation number sequence synced to high-water mark <N>.`), so no manual step
is required. Verify that line appears, then confirm the next organic quotation
lands above the imported range before going live.

If you ever need to re-sync by hand (e.g. after a manual `number` edit), the
equivalent is idempotent — `setval` to the current max is a no-op on re-run:

```bash
uv run python manage.py dbshell -c \
  "SELECT setval('quotation_number_seq', (SELECT COALESCE(MAX(number), 1) FROM reservations_quotation));"
```

The Enquiry/Payment/Refund/SecurityDeposit reference sequences (BUG-007) need
**no** equivalent sync. Payment/Refund/SecurityDeposit loaders set no
`reference` (all organic), and imported Enquiry references are the legacy
`EnquiryNo` — bare numerics (1501–2176 in the reference dump, equal to the
`QuotationNo` where quoted; the `E-{Id:06d}` fallback for a blank `EnquiryNo`
never fires on it) — disjoint from the organic `E-{year}-{n}` shape, so an
organic reference can never collide with an imported one.

## 4d. Customers load straight to `Person` (GAP-045)

`VillaClientDetails` no longer loads to a `reservations.Guest` — `ClientLoader`
writes a unified `accounts.Person` **directly**, keyed `legacy_id="client-{Id}"`
with `kind=CUSTOMER`, reconciling each row's single legacy email/phone onto a
PRIMARY `PersonEmail`/`PersonPhone` child in place (idempotent on re-run). The
downstream loaders resolve their customer FK through `person_for_client("{Id}")`
→ that same `client-{Id}` Person, falling back to the `unknown_client` sentinel
rather than dropping the referencing row.

> **The customer chain has two extra hops since GAP-108** (U8b, U8d). From
> ~Nov-2025 the legacy app stopped writing a name onto `VillaClientDetails`, and
> often stopped naming a client row at all, so the plain lookup above
> increasingly landed on the sentinel. Two loaders now reach one hop further
> before giving up, and neither can merge two real people:
>
> - **`ClientLoader`** takes the name of the lowest-Id named live enquiry
>   reached through the client's own quotations — 111 clients name themselves,
>   920 more are recovered this way, and the remaining 184 have no name anywhere
>   (see `Person (client)` in [§5](#5-verify-with-reconcile_legacy)).
> - **`QuotationLoader`** resolves a client-less quotation through its enquiry,
>   which is what closed the old `Quotation` gap of 9 to **0**.
> - **`GuestPreferenceLoader`** resolves client → **the preference's own
>   quotation's person** → sentinel, bounded by `_may_borrow_quotation_person`:
>   the hop is allowed only when the preference names no real client row at all,
>   or when the quotation names that same client. A preference on a client row
>   that exists but did not load keeps the sentinel rather than attaching one
>   person's dietary/access/VIP notes to another. This moved preferences on the
>   sentinel from 498 to **30**, spread over 104 real people, without moving any
>   reconcile count. The run logs
>   `data_migration.preference_customer_borrowed_from_quotation` with `count`
>   and `refused` (`count=514, refused=0` on ResProd) so a newer dump shows the hop's
>   reach directly instead of surfacing it as a moved gap.
>
> Registry order is load-bearing for the last one: `quotation` runs before
> `guest_preference`, so `Quotation.person` is already resolved when the
> preference loader reads it.
>
> **A quotation line's party hops the same way (GAP-118 §4).** A
> `VillaQuotationMaster` with **both** `Adult` and `Children` NULL takes the
> party from its own `VillaEnquire` row, read down a `LEFT JOIN … AND
> e.DeletedAt IS NULL` — never from the loaded `Enquiry`, whose `adults`
> defaults to 2 and would hand every `-autoenquiry` stand-in the fabricated
> party BUG-030 §23 bans. An **explicit** `Adult=0` still loads as 0; a
> half-filled master keeps the half it has; an out-of-range web-form value is
> left unborrowed rather than dropping the line on write. The run logs
> `data_migration.quotation_line_party_from_enquiry` with `count`, the same
> way the hops above report their reach — measure it on the day rather than
> pinning §4's headline 1 235, which counts a wider population.
> `reconcile_legacy` prints the residual zero-party lines informationally.
>
> **The enquiry hop misses at load time for sheet-born customers (GAP-112).**
> `EnquiryLoader` matches with `match_person_by_email(active_only=True)`, but
> the `sheet-person-…` people it would match do not exist until the sheet
> imports run, so `Enquiry.person` stays NULL and `QuotationLoader` has nothing
> to hop to. The `relink_enquiry_customers` step
> ([§4](#4-run-every-loader)) closes that after the fact with the same matcher,
> plus one veto the loader lacks: an address held by **more than one** person
> (whatever their kind or status) is never resolved — the matcher's
> CUSTOMER-first tie-break is fine for a loader but is a guess for a relink.
> A relinked enquiry's sentinel quotations follow it, and so do the sentinel
> guest preferences recorded against those quotations (the loader borrowed
> the sentinel from that very quotation); a preference whose quotation stays
> on the sentinel is not touched. The shared-address leftovers are
> [§6g](#6g-post-load-person-merges-bug-030-18) merge candidates; a
> names-disagree one has a single holder, so there is nothing to merge — staff
> compare the enquiry's name with that person and link it by hand, or not. Minting a Person per
> enquiry inside `loadlegacy` was rejected: ~2 700 people duplicating the ones
> the sheet import creates properly.

The cutover **order is load-bearing**: `migrate` MUST run before `loadlegacy`:

```bash
uv run python manage.py migrate           # includes the D5-4c re-key migration
uv run python manage.py loadlegacy --all
```

`ClientLoader` is registered ahead of the preference / finance / booking loaders
in `registry.py`, so every `client-{Id}` Person exists before a downstream loader
resolves it.

**The `Guest` model is retired (GAP-045 D5-4c).** Customers load straight to
`Person`; there is no `Guest` table, no `_guest_post_save` mirror signal, and no
`link_person_fks` command anymore.

**One-shot re-key migration.** _(Historical — folded into the flattened
`0001_initial` on 2026-07-08; a fresh DB has no `guest-` rows so there is
nothing to re-key. Retained here as the record of what the one-shot did.)_
Reservations migration
`0035_remove_guestpreference_guest_remove_booking_guest_and_more` did two
things, in order: (1) re-keys every legacy guest-mirror Person from
`legacy_id="guest-{pk}"` onto the unified `client-{VillaClientDetails.Id}`
namespace (or NULL when the source Guest had no legacy id — never the literal
`client-None`), then (2) drops the `guest` FK from the five reservation models and
deletes the `Guest` model. On a fresh Postgres there are no `guest-` rows so the
re-key is a no-op, but on an existing DB it MUST run **before** any `ClientLoader`
pass — running a loader first could write a `client-{Id}` row that the re-key
would then collide with; the migration **fails closed** (raises) on such a
collision rather than minting a silent duplicate customer. The canonical
`migrate`-then-`loadlegacy` order above guarantees this never fires.

**Dedup customers via `/contacts`.** With Guest gone, duplicate customers are
collapsed through the `/contacts/{id}:merge` verb (canonical `Person.merge`,
GAP-045 D1) — the same destructive FK-rewrite-then-hard-delete path used for
owner/agent contacts. There is no separate guest-dedup tool.

In `reconcile_legacy`, `VillaClientDetails` is checked against the `client-`
slice of `Person` (`expected_gap=184` on ResProd — the rows that name nobody on
either side), and the `VillaContact` owner/agent check excludes that slice — see
the two `Person (...)` rows in [§5](#5-verify-with-reconcile_legacy).

## 4e. Free-text companies fold into `Organisation` (GAP-046)

`VillaContact.Company` is no longer copied into a free-text `Person.company`
column. `ContactLoader` routes each non-blank company string through
`accounts.services.organisations.organisation_for_company_name`, which
get-or-creates a deduped `Organisation(org_type=agency)` keyed on a content hash
of the **case/whitespace-normalised** name (`dedup_key`, never `legacy_id`) and
links the contact via `Person.agency`. A blank company → `None` → null agency.
The placeholders `NA`, `N/A` and `-` (any case, stripped; 226/233 rows in the
reference dump are `NA`) count as blank too (BUG-030 §15, `COMPANY_PLACEHOLDERS`
in `loaders/people.py`), and the `Organisation (agency)` check excludes them.
The `get_or_create` runs inside the same per-row savepoint as the `Person`
write, so a failed contact row rolls its org back too — no orphan organisations.

Only **exact** (normalised) name matches dedupe automatically. Genuine
near-duplicates ("Dune Travel" vs "Dune Travel Ltd") are left intact and
surfaced for human review — run the **read-only** reporter after the load:

```bash
uv run python manage.py dedupe_organisations            # all org types
uv run python manage.py dedupe_organisations --org-type agency --threshold 0.9
```

It never merges; fold a confirmed duplicate with `POST /organisations/{id}:merge`
(admin-only). `reconcile_legacy` includes an `Organisation (agency)` check
(distinct normalised `VillaContact.Company` vs loaded agency count) so a silent
"zero orgs created" regression turns the cutover RED.

**Existing-DB upgrade (no fresh rebuild):** _(Historical — this in-place-upgrade
migration was folded into the flattened `0001_initial` on 2026-07-08 and no
longer exists as a standalone step. A fresh rebuild via the loaders above
already populates `Person.agency` directly. Retained as the record of the
one-shot backfill's contract.)_ migration
`accounts/0012_drop_person_company` was the company→agency backfill for an
already-loaded DB. Its `RunPython` recomputes the SAME `company_dedup_key`
(a frozen, sync-tested copy of `accounts.services.organisations.company_dedup_key`)
to get-or-create the deduped agency `Organisation` and link `Person.agency`, then
its `RemoveField` drops `Person.company` — in that order. Idempotent and
collision-safe (case/whitespace variants converge on one row; an already-linked
Person is skipped). So both paths — a fresh rebuild via the loaders above and an
in-place `migrate` of an existing DB — populate `Person.agency`.

## 4f. Property-contact role taxonomy reconciled (GAP-048)

`PropertyContactAssignmentLoader` now maps the legacy `VillaRoles` ids **1:1** to
`accounts.ContactRole` (`_role_for` / `_ROLE_MAP` in
`data_migration/loaders/reservations.py`):

| Legacy id | Legacy name        | ContactRole          |
|-----------|--------------------|----------------------|
| 1         | Owner              | `owner`              |
| 2         | Agent              | `agent`              |
| 3         | Villa Admin        | `villa_admin`        |
| 4         | Villa Manager      | `manager`            |
| 5         | Management Company | `management_company` |

This **corrects** the earlier map, which collapsed id 3 → `manager` and id 5 →
`owners_rep`. Because cutover has **not** run, this is a forward-only fix — the
next full `loadlegacy` emits the right roles, so no back-migration is needed.
`villa_admin` and `management_company` are new `ContactRole` members
(`accounts/enums.py`); the choices change is a state-only `AlterField`
(`properties/0021_reconcile_contact_role_choices`, reversible). `housekeeper` and
`owners_rep` remain valid roles with **no legacy source** (kept per
`django_res_design/design/decisions.md`) — they are only ever set in the new system,
never emitted by the loader. An unmapped/NULL legacy `RoleId` falls back to
`owner`.

> ✅ **Resolved 2026-07-05 (dry run against the live dump):** the live
> `VillaContactMapping` has **no `RoleId` column at all** — the schema doc's
> claim was wrong for this vintage; roles live only in the child
> `VillaContactRoleMapping`, exactly where the loader reads them. 3 of 335
> mappings have no role child and fall back to `owner` (accepted). The
> mapping's `GroupId`, all 12 `IsAccess*`/`IsNotify*` flags and `Notes` are
> zero-use in the dump, so the loader dropping them loses nothing. No
> COALESCE change needed.

## 4g. Chargeable Extras → `BookingChargeItem` (GAP-017)

> **SUPERSEDED — this step does not run at cutover (GAP-108 U1, 2026-09-16).**
> `BookingChargeItemLoader` is **unregistered**, along with the Booking and
> Payment loaders: historic stays now arrive from the Past Bookers spreadsheet
> as `PastStay` rows (GAP-089), so there are no imported Bookings for a charge
> line to hang off. [§5](#5-verify-with-reconcile_legacy) mechanises that with
> three inverted invariants — `Booking` / `Payment` / `BookingChargeItem with
> legacy_id` must all be **0**, and a non-zero count means a booking loader was
> run against the legacy DB.
>
> The loader module, its tests and this section are kept as the **schema
> record**: they are the authoritative description of `VillaBookingDetails` and
> of the currency policy below, and they are what a future "enrich past stays
> from `VillaArchiveBookings`" ticket would build on. Nothing here is executed
> today. The dates, amount and currency of the re-keyed stays in
> `VillaArchiveBookings` now reach `PastStay` through `import_archive_stays`
> ([§4](#4-run-every-loader), GAP-113); chargeable extras still do not.
> For the *villa* extras catalogue that **is** loaded, see
> [§4i](#4i-extras-catalogue--pricingextra-gap-107) — a different table
> (`VillaSeasonRate` with `IsExTra = 1`) and a different destination
> (`pricing.Extra`).

`BookingChargeItemLoader` ports the staff-entered "Chargeable Extras"
(`VillaBookingDetails`: `Id, BookingId, CurrencyId, Price, Notes`) onto
`reservations.BookingChargeItem`. It runs after `PaymentLoader` in the
registry (bookings and their payments must exist first). Mapping:
`Notes → label` (stripped, truncated to 200 chars — overflow text is
preserved in `notes`), `Price → amount` (signed), `Id → legacy_id`.
Same-currency lines port **verbatim**, which reproduces legacy's displayed
total by construction: legacy showed `RentalPrice + Σ details`, and the new
total is `balance_due + Σ charge_items` with `balance_due` loaded from
`RentalPrice`.

**Currency policy (convert-or-flag — mismatched rows are never written
verbatim):**

- `CurrencyId` 0/NULL → treated as booking-currency (legacy summed these
  rows blind into the booking total, so booking-currency is what they
  meant). A *non-zero* `CurrencyId` with no matching `Currency` is an error
  row, not a silent fallback.
- Row currency ≠ booking currency → converted via `FxConverter` at the rate
  most recent **on/before `booking.date_from`** (pinned so the load is
  deterministic), quantised to the booking currency, with provenance appended
  to `notes` (`Imported from legacy: 100.00 USD @ 0.8 (as of 2026-06-01).`).
  These bookings' totals **deliberately differ from legacy**, whose blind
  cross-currency sum was a latent bug.
- **FX prerequisite:** rates must exist in the **row → booking** direction
  (no inverse fallback) with `as_of ≤ booking.date_from`. Seeding today's
  rate clears nothing for historical bookings — seed `FxRate` rows dated at
  or before the earliest affected `date_from`, then re-run. Until then each
  mismatched row lands in the loader's `errors` count
  (`data_migration.charge_item_fx_failed`, `reason="no_rate"`).
- A conversion that quantises to zero is skipped with a warning (the model's
  `amount != 0` constraint forbids the write).

**Payment-schedule resync is suppressed during the load.** Charge-item writes
fire `booking_total_changed`, whose receiver rewrites PENDING payments
(`PaymentScheduler.resync_for_booking`) and resizes pre-charge security
deposits — and imported bookings *do* hold PENDING BALANCE rows, so an
unsuppressed load would rewrite legacy payment amounts. The loader
disconnects the `payments.resync_on_booking_total_changed` receiver around
its row loop and reconnects it after (the package's first signal
suppression; earlier notes claiming the loaders "already run with signal
discipline" were aspirational). Everything else about the
package's service-bypass convention holds: no `BookingEvent` rows, AuditLog
still captures via tracked-model `pre_save`.

**Removal sweep:** each run hard-deletes previously-imported rows
(`legacy_id IS NOT NULL`) whose legacy source has vanished **or** now fails
transform (zero price, FX-rounded-to-zero) — so a re-run converges on the
legacy state. Staff-created rows (`legacy_id IS NULL`) are never touched.
Zero-`Price` legacy rows are skipped (counted in `skipped`).

**Accepted side-effects** (documented, not engineered around):

- The loader bypasses `ChargeItemService._check_total`, so an imported
  booking can carry `balance_due + Σ charges < 0`. Safe downstream (resync
  clamps ≥ 0; the API renders a negative string), but a later staff charge
  write via the API on such a booking can 400.
- Imported bookings are DRAFT and the charge service's state gate rejects
  DRAFT, so imported lines are API-immutable — desirable for historical data.

## 4h. Open product decision — property-level POA (DEFERRED)

`VillaWebsitePricing.IsPOA` is a curator-set, property-wide "price on
application" flag on **18 live villas**. It is **not** derivable from the
rate-level `RateBand.is_poa` (COVERAGE item 4), and the new schema has no
property-level home for it. **Decision 2026-07-06: DEFERRED** pending a call
on whether to add a `Property.is_poa` flag.

- **Impact if cutover proceeds un-resolved:** those 18 villas will show a
  computed price on the customer site instead of the legacy "price on
  application / enquire" treatment — a customer-facing behavioural regression
  (`feedback_follow_legacy_customer_facing`). This is a **tracked open item**,
  not a silent drop.
- **To resolve:** add `Property.is_poa = BooleanField(default=False)` +
  migration, extend `PropertyLoader` to read `VillaWebsitePricing.IsPOA`
  (MAX(Id) per `VillaId`), and have the guest-side price surface honour it.
  Then move this from "deferred" to "loaded" in COVERAGE item 4.

## 4i. Extras catalogue → `pricing.Extra` (GAP-107)

`ExtraLoader` (`extra`, registered after `rate_rule`) ports the villa
**menu** of extras — the `VillaSeasonRate` rows flagged `IsExTra = 1` that
`RateBandLoader` keeps out of the rate grid (85 live rows on loaded villas on
the ResProd 13-Aug-2026 dump; 96 on the 24-Apr-2025
dump, 84 of them on villas that load — the 137 older docs quote was a parse
of the git-tracked `DbScript.sql`; census in `DRYRUN_LOG.md` run 3). Booked extras are a different thing and were already ported by
[4g](#4g-chargeable-extras--bookingchargeitem-gap-017). Legacy folded these
rows in from the pre-2022 `tblPropertyExtra` with junk `FromDate`/`ToDate`
(the 2022 migration run date), `CurrencyId = 0` and `SeasonId = 0`, and its
Extras UI only ever edited `Name` / `Description` / `Price`, so a ported
extra is deliberately minimal and **opt-in**:

| `Extra` field | Value | Why |
|---|---|---|
| `legacy_id` | `ID` (the rate-table pk, same as `rate_rule`) | `OldId_ExtraRate` is the pre-2022 `tblPropertyExtra.Id` (0 for UI-created rows) and is not read. |
| `name` | `Name`, else `Description`, else `Extra <ID>`; truncated to 128 | `Name` is `nvarchar(max)`. |
| `description` | `Description` | |
| `kind` / `calc` | `other` / `fixed_per_stay` | Legacy has no unit; staff refine in the SPA (no name-based inference). |
| `amount` | `Price` as entered (`NULL → 0`) | `RatesModel.Calculate()` is not reproduced. Census re-run on ResProd (13-Aug-2026, extras on loaded villas): `PriceType` is gross (20) on **83** of 85 rows, 82 of them priced, and net (10) on **2** — ids 5238 and 5341, both still `Price = 0.00`, so **no net row carries a price to under-quote**. `TaxAmount` is 0 throughout. Porting `Price` verbatim is therefore exact for every priced extra on this dump. (24-Apr-2025 for comparison: 87 gross / 9 net of 96, same two priced-net-free ids.) **Recalibrating on a newer dump: re-run the net-rows census** — `PriceType = 10 AND Price > 0` on live villas must stay empty, or `amount` under-quotes those rows by their commission. |
| `currency` | legacy `CurrencyId` if non-zero, else `resolve_property_currency` (preferred live plan → settings → EUR) | The engine filters extras by exact currency match, so the extra must land in the currency quotes are built in. No resolvable currency → skipped. Snapshotted at load: a villa with a *scheduled* currency switch (future-dated plan in another currency) needs its extras re-currencied in the SPA when the switch lands — the engine will not see them until then. |
| `is_mandatory` | `False` | Legacy extras were a menu, never auto-charged. **Consequence:** the SPA quote builder never sends `opt_in_extras`, so ported extras are catalogue + Zoho `extras[]` visibility until the FE follow-up ticket wires opt-in selection. |
| `commissionable` | `True` | GAP-076 default. |
| `applies_from` / `applies_to` | `NULL` | The legacy dates are the 2022 fold timestamp; porting them would make the engine drop every extra. |
| `min_party` / `max_party` | `NULL` | |
| `is_active` | `True` | Only `DeletedAt IS NULL` rows load; every run retires ported extras absent from the result set (see below). |
| `sort_order` | dense `0..n` per villa in `ID` order | Keeps legacy creation order (Zoho orders `extras[]` by it) without the thousands-wide gap that would put every staff-created extra (default `0`) ahead of the ported catalogue. Create-only. |

**Upserts never clobber staff refinements.** Only `name`, `description` and
`amount` — the fields legacy can actually change — are refreshed on an
existing row; `kind`, `calc`, `is_mandatory`, the window, the party bounds,
`sort_order`, `is_active` and `currency` are create-only, so staff can
classify and window a ported extra in the SPA and a later run keeps it.
Unlike `rate_rule` this is an upsert, not a full replace.

**Dropped: the legacy discount columns** (`IsDiscount` / `DiscountRate` /
`DiscountType` / `DiscountApply` / `DiscountNight` on the same table). GAP-009
established legacy stored them but never applied them (`RatesModel.Calculate()`
reads `DiscountType` into an enum and stops), so there is nothing to port.
`pricing.Discount` starts empty for migrated villas.

**Retirement:** the loader filters `DeletedAt IS NULL`, so a legacy-deleted
extra never appears in the result set. The retire sweep always runs: it sets
`is_active=False` on every ported extra missing from the set
(`data_migration.extras_retired` log event).

## 5. Verify with `reconcile_legacy`

```bash
uv run python manage.py reconcile_legacy --integrations
```

The command enforces the tables below itself: it prints an `expected`/`status`
column and **exits non-zero** if any row's `gap != expected_gap`, so this step
passes iff the command succeeds — no manual cross-reference needed.
`--integrations` adds the Zoho continuity section ([§4b](#4b-capture-external-ids-into-syncrecord-zoho),
blocking) and the WordPress surface section (informational).

The numbers live in `reconcile_legacy.py` (`_CHECKS`), which is their single
source of truth; each check carries its itemised derivation as a comment. The
tables here are a human-readable mirror, and
`test_documented_expected_gaps_are_encoded` pins the whole set — so a number
that legitimately shifts on a newer dump is re-derived in the code *and* that
test, never nudged in this file alone.

> **Every number below was re-pinned in GAP-108 against `ResProd`** (13-Aug-2026
> production data, loaded 2026-09-16), itemised to zero residual. Figures quoted
> in older notes were calibrated on the 24-Apr-2025 `NewResSystem` dump and no
> longer apply: most moved because the loaders gained ResProd's soft-delete
> filters, one (`RateBand`) because the check's own legacy query was wrong.
> `gap = legacy_count - loaded_count`, so a negative gap means the loaded side
> is deliberately bigger. The loaded side now defaults to
> `legacy_id IS NOT NULL`, so staff rows, `createsuperuser` and the sheet
> imports can never move a gap between runs. The one deliberate exception is
> the GAP-112 invariant below, which the sheet imports raise (as can
> `QuotationLoader`'s back-fill of an enquiry from a later quotation) and
> `relink_enquiry_customers` returns to 0.

### Expected gaps — the 16 checks that are non-zero

| Check | Expected gap | Reason |
|-------|--------------|--------|
| `Country (legacy)` | **−225** | Structural, not a loss: `properties.0002` pre-seeds 249 canonical ISO-3166 countries and legacy `VillaCountry` rows are matched *onto* that seed by iso2 rather than added to it, so the loaded side is bigger. ResProd has 24 legacy rows — the 23 of the old dump plus Id 25 `Sync_Country`, a soft-deleted sync artefact resolving to no ISO code — hence 24 − 249. The lazily-minted `XX` sentinel is excluded on the loaded side by `iso2`. The constant tracks the **seed**: it moves only when `properties.0002` changes or legacy gains/loses a country row. |
| `Currency` | 4 | The rows `CurrencyLoader` refuses: three soft-deleted junk codes that are not 3-letter alphabetic (`HTFG` Id 4, `RUPEE` 5, `RS` 7) plus the soft-deleted `EUR` twin (Id 2) — the live EUR (Id 3) claims the code first (BUG-028). |
| `PersonEmail` | 2 | 319 legacy `VillaContactEmail` rows, 317 loaded. Both skips are rows with no `@`: Id 30 (empty string) and Id 270 (the literal `tbc`). |
| `PersonPhone` | 8 | 259 legacy `VillaContactTele` rows, 251 loaded: 7 blank numbers plus Id 221, whose `ContactId` matches no `VillaContact` row, so it has no person to hang on. |
| `CollectionMembership` | 9 | 2 206 `VillaCollectionsMappings` rows − 194 `IsActive = 0` − 921 `IsActive IS NULL` = 1 091 active; loaded = 1 082 distinct (villa, collection) pairs on a live collection and a loaded villa. Legacy's own views read `isnull(IsActive,0) = 1`, so **NULL is inactive** and the loader mirrors that — see the note under the table, because that convention costs real memberships. (Pre-GAP-108 this was 308 on the 24-Apr dump, dominated by five collections deleted together on 2024-05-28.) |
| `Room` | 321 | 2 714 legacy rooms − 30 `IsActive = 0` = 2 684 active; 321 of those sit on a villa the property loader does not load (soft-deleted, or the blank-name row), so they have no parent to attach to. |
| `Room placement (GAP-065)` | 61 | A no-loss gate: every legacy room with a `PlacementId` must land with the raw string preserved in `placement_note`. 2 409 active rooms carry one; the 61 are either (a) on an unloaded villa — the `Room` gap above, restricted to placement-bearing rows — or (b) a dangling `PlacementId` whose `VillaRoomsPlacement.Name` is NULL/blank, where the LEFT JOIN keeps the room and the note is honestly empty. The loaded side counts only the legacy slice, because `placement_note` is API-writable. |
| `PropertyImage` | 839 | 19 071 legacy rows, 18 232 loaded. All 839 sit on the 35 soft-deleted villas `live_villa_sql` excludes — **0** are empty filenames and **0** are on a live villa, so no loaded property loses an image. |
| `PropertyNearbyPlace` | 78 | 178 `VillaNearBy` rows − 1 inactive = 177; 78 hit one of the loader's three skips (parent property unresolved, place type unresolved, empty name). |
| `RateBand` | 462 | **Legacy query replaced in GAP-108** — the old one counted a 39 868-row universe that was never the loader's input, so both numbers documented against it (gap 4492, then 33 235) are dead. Real universe = 6 398 non-occupancy parents + 697 valid occupancy children (which replace 302 parents) = 7 095; loaded 6 633. Itemised to zero residual: **+495** flattener-shadowed sources (481 parents + 14 occupancy children that won no (date × party) cell because a higher-precedence sibling on the same regime plan covered them whole), **−8** synthetic `occ-fb-*` fallbacks the occupancy expansion adds for party ranges a villa's own bands leave uncovered, **−25** `#seg` fragments where one source survives in more than one flat cell. Cross-check: 7 095 − 495 = 6 600 surviving sources, +8 = 6 608 (the loader's `created`), +25 = 6 633 rows. The loader's `skipped` and `party_clipped` counters are **not** terms in it. |
| `RateBand indicative (CarriedRates)` | 195 | **GAP-114.** The `RateBand` universe above narrowed to rows on a `VillaSeason.CarriedRates` season (`ISNULL(s.CarriedRates, 0) = 1` on both halves — the column is a nullable ResProd-only bit the loader reads as "not carried" when NULL) against loaded bands with `legacy_id` and `is_indicative = True`. ResProd 16-Sep-2026: 1 616 carried sources (1 465 parents + 151 occupancy children on the 198 flagged seasons), 1 421 indicative bands. The same replay as the `RateBand` row, restricted to carried sources, itemises it to zero residual: **+218** flattener-shadowed carried sources (206 parents + 12 occupancy children, of the 495), **−2** `occ-fb-*` fallbacks minted under a carried parent (of the 8), **−21** `#seg` fragments of carried sources (of the 25 — the copied-forward grids are where sibling seasons overlap most). Cross-check: 1 616 − 218 = 1 398 surviving carried sources, +2 +21 = 1 421. A staff carry-forward also writes indicative bands, but with no `legacy_id`, so it never moves this row. |
| `PropertyContactAssignment` | 6 | Both sides count (mapping, role) **composites** — the loader writes one row per role, so counting bare mappings (what this check did before GAP-108, and the reason its old "composite collapse" note was wrong) never matched. 466 mappings (23 role-less, 435 with one role, 8 with two) → 474 composites with no duplicates; 6 sit on soft-deleted villas 462 (3), 505 (2) and 510 (1). Every mapped contact has a name, and the blank-name villa has no mapping. |
| `Person (client)` | 184 | 1 215 `VillaClientDetails` rows, 1 031 loaded. Only 111 clients carry their own name; **U8b** recovers 920 more by borrowing the name of the lowest-Id named live enquiry reached through the client's quotations (from ~Nov-2025 the legacy app stopped writing a name onto the client row). The remaining 184 have no name anywhere to take — test accounts, `info@`-style shared addresses, and rows whose quotations reach no named enquiry; `ClientLoader.transform` returns `None` rather than minting a nameless Person. |
| `PropertyFinance` | 1239 | 1 597 rows with `VillaId IS NOT NULL` (= every row; the column is `NOT NULL`) − 413 `VillaId = 0` with a NULL `ParentId` (contact-default templates) − 676 `VillaId = 0` with a `ParentId` (parent-child overrides owning no villa) − 150 `VillaId > 0` on a villa `live_villa_sql` excludes = 358 stamped per-villa rows. Override rows with `VillaId > 0` **are** ported as the villa's own row — never exclude on `ParentId`. Only rows the per-villa pass stamps with `legacy_id` count on the loaded side, so the GAP-070 owner-template and `snapshot_defaults` rows (both NULL) can't move it. `loaded = 0` means a DB loaded before `properties.0008` — see [§6f](#6f-re-stamp-propertyfinancelegacy_id-after-gap-107-only-for-dbs-loaded-before-2026-09). |
| `QuotationLine` | 345 | 8 035 `VillaQuotationDetails` rows, 7 690 loaded; every skip is the single FK guard in `transform`, zero residual: **206** on a soft-deleted `VillaQuotationMaster` that `QuotationLoader` never loads, **79** orphans whose `QuotationMasterId` matches no master at all (173 distinct dangling ids — legacy has no FK here), **53** on a live loaded quote pointing at villa 462 or 505 (the two deleted test villas, so no real villa loses a line), **7** with `VillaId` 0/NULL. After U8b fills a missing stay date from the master, both date guards and the currency guard fire **zero** times. |
| `GuestPreference` | 201 | 836 `ClientPreferenceDetails` rows, 635 loaded; every skip is a collapse onto the `unique_person_preference` triple (person, preference type, quotation) or a dangling FK, zero residual: **149** exact duplicate legacy rows — the legacy screen re-saves and the table has no unique constraint, so one client wrote the same VIP note 25 times; **38** distinct unloaded client ids collapsing onto the single unknown-client sentinel (all `quotation = NULL`); **12** same client with two different unresolved quotations, both flattened to `quotation = NULL` and so merged; **2** dangling `ClientPrefMasterId` 12 and 13 (`VillaClientPrefMaster` has 11 rows, max Id 11). The count is order-independent (skips = rows − distinct triples), which is why **U8d**'s quotation fallback re-keys 474 triples onto a real person without moving it. |

> **`IsActive IS NULL` costs live-looking collection memberships.** 921 of the
> 2 206 mapping rows carry a NULL flag, and legacy's own `isnull(IsActive,0) = 1`
> convention hides every one of them from the legacy UI too — so the loader
> drops them and the check agrees. They are **not** part of the 9 above: the
> legacy side filters them before the comparison. But 612 of them do sit on a
> live collection and a loaded villa, and **178 distinct (villa, collection)
> pairs exist *only* as NULL rows** — no active row anywhere reinstates them, so
> those 178 memberships are the real loss. If a collection looks thin after
> cutover, this is why; reinstating them is a product decision, not a loader
> bug.

### Invariants — legacy side is a literal `SELECT 0`, so any row is a blocker

These mechanise claims the row counts cannot: each asserts that a **loaded**
query returns nothing.

| Invariant | What a non-zero result means |
|-----------|------------------------------|
| `Person (owner/agent) primary email count != 1` | An owner/agent with ≥1 loaded email has no primary (the partial unique constraint already rules out two) — `ContactEmailLoader` demotes rivals but never promotes. |
| `Organisation named NA / N/A / -` | A placeholder company name became a real `Organisation`; `_company_name` maps those to no agency (BUG-030 §15). |
| `Property slug containing ://` | An imported slug is a raw WordPress URL rather than a slugified one — 385 of 386 loaded villas carry `://` in legacy `VillaMaster.Slug`, so this guards every later write too. |
| `RatePlan non-GROSS basis` | An imported plan lost its explicit GROSS stamp and fell back to the model default (SMELL-021 — legacy cannot express NET). |
| `RateBand non-POA priced <= 0` | An imported non-POA band would quote a free stay (BUG-028). |
| `RateBand unapproved imported` | An imported band is unapproved, so the engine would never price it — legacy quotes ignore `IsApprove` (BUG-028 §5). |
| `PropertyFinance NULL calculation type` | A stamped finance row would fall through to `_POLICY_FALLBACKS`, turning "10 %" into EUR 10 (BUG-028). |
| `PropertySettings without currency` | A property's settings row resolved no currency — the flagged `IsDefaultSettingCurrencyId` case that must take the CPD currency (BUG-028). |
| `Booking with legacy_id` | A booking loader ran against the legacy DB. It is unregistered (GAP-089): historic stays arrive from the Past Bookers sheet as `PastStay` rows, which carry no `legacy_id`. |
| `Payment with legacy_id` | As above, for `Payment`. |
| `BookingChargeItem with legacy_id` | As above, for `BookingChargeItem`. |
| `Quotation on unknown client with a relinkable enquiry` | The `relink_enquiry_customers` step ([§4](#4-run-every-loader), GAP-112) was skipped or has gone stale: a loaded quotation is still on the unknown-client sentinel although its enquiry has a person, or is one the relink would link now (268 on the run-5 DB before the step). **The usual cause of a small non-zero here is a missed *second* relink** — `import_archive_stays` mints people after the first one, so run 8 sat at 2 until the relink was run again ([§4](#4-run-every-loader)). The ambiguous and unresolvable remainder (53 there) is deliberately not counted — it depends on the sheet contents and moves with §6g merges. |

Two further checks compare a **value**, not a count, because a count would pass
vacuously: `Currency EUR legacy_id (live row)` (legacy `MIN(Id)` for a live
`EUR` — Id 3 — vs the `legacy_id` stamped on EUR; a gap names the soft-deleted
Id 2 twin, BUG-028) and `PropertyDefaults currency legacy_id (CPD row)` (the
`VillaConfigPropertyDefault` currency vs the singleton's — a row count is
meaningless because `get_solo()` auto-creates the singleton).

### Zero-gap checks worth knowing

The remaining checks expect **0**, and several encode real behaviour rather
than a tautology:

- **`Country (active)` / `Region (imported)` / `Region (active)`** — deleted
  countries and regions load **retired** (`is_active=False`), never skipped, so
  FKs still resolve; the active slices pin the retired counts by subtraction. A
  live legacy row `CountryLoader` cannot seed-match (iso-less, or a second row
  on a claimed iso2) is skipped and logged. England (24, `UK`) resolves to GB,
  so [§7](#7-england--gb-merge-retired--bug-030-6) stays retired.
  **Ops:** a reload that retires rows does not reach Zoho — run
  `zoho_backfill --kinds villa,enquiry,contact` afterwards so Limitless stops
  offering retired regions.
- **`Property` (was 1)** — the blank-name villa skip moved into the shared
  `live_villa_sql` helper, so it is no longer an unexplained one-row gap.
- **`Quotation` (was 9)** — U8b resolves the 9 quotations with
  `ClientDetailsId = 0` through their enquiry instead of dropping them.
- **`Enquiry` (was −5)** — no booking-synth stand-ins exist any more.
- **`PropertyFeature`** — inactive mappings (262 on ResProd) are filtered; a
  soft-deleted feature still resolves to its lowest-Id live namesake, so the
  structural gap stays 0.
- **`PropertyLocation` / `PropertyCapacity` / `PropertySettings` / `RoomBeds` /
  `PropertyDescription` / `PropertyService`** — GAP-108 additions covering the
  satellite rows the loaders write per property or per room, which previously
  had no check at all.
- **`Extra`** — live legacy extras on loaded villas vs `pricing.Extra` rows with
  a `legacy_id` **and** `is_active=True`; a full run retires legacy-deleted
  extras by flag. Mapping in [4i](#4i-extras-catalogue--pricingextra-gap-107).
- **`VillaAvailability (future days)`** — future day rows deduped to the latest
  edit per (villa, day) by `COALESCE(UpdatedAt, CreatedAt), Id`, filtered to the
  blocking statuses, coalesced into `BookingHold(reason=MANUAL)` runs and split
  around imported bookings and unreleased staff holds. **Both sides move with
  "today" — run the load and the reconcile on the same day.**

**A known, deliberate inconsistency no count check can see:**
`Person`, `Enquiry` and `Quotation` all have `created_at` back-stamped from
their legacy `CreatedAt` (BUG-030 §28 — `auto_now_add` ignores assignment, so
each loader re-`update()`s the row), but **`QuotationLine.created_at` is the
load day** on every row. This is not an oversight in the loader:
`VillaQuotationDetails` **has no `CreatedAt` column**, so there is nothing on
the line to back-stamp from. The consequence is narrow but real — a line looks
newer than the quotation that owns it, so any report ordering or ageing
*lines* by `created_at` will bucket the entire legacy history into cutover day.
If that matters, the fix is to stamp each line from its parent quotation's
`CreatedAt` (in legacy a line is created with its master, on the same screen);
it moves no counts and no money, so it is safe to do later on a reload.

### `RatePeriod` night parity

Printed as its own table after the row counts. For every villa it compares the
nights legacy priced — the coalesced union of its live, priced, non-extra rate
spans (`PRICED_ROW_PREDICATE`, legacy `ToDate` inclusive) — against the nights
the villa's loaded legacy `RatePeriod` rows cover. Boundary trims and conflict
splits never change that night *set*, so a mismatch means the villa lost or
invented priced nights in the GAP-110 regroup. A clean run prints `OK — every
villa's loaded periods cover exactly its legacy nights`; otherwise every
mismatched villa is listed with its legacy vs loaded night counts and is **one
blocker each**. Expected residue is zero — itemise per villa, never wave it
through.

### Archive stays (GAP-113)

Printed after the night-parity table (and before the `--integrations`
sections). It reads `VillaArchiveBookings` and runs the same
classification as `import_archive_stays` ([§4](#4-run-every-loader)). Blockers:

- stays still classed **enrich** or **create**: the import was skipped, or a
  stay rolled back. One blocker per category, naming the first 10 ids.
- archive rows that **cannot be parsed**: they can never land.

The skip categories and the test row are listed but do not block, because
they depend on the sheet contents. A clean run after the import shows only
`exists` plus those skips (run 6: 248 exists, 4 `bn_year_conflict`, 1
`weak_conflict`, test row 297).

A stay the importer skipped for its **person** (`person_ambiguous`,
`person_inactive`) or for a row error is still classed enrich or create, so
it keeps blocking. It would otherwise be missing from that guest's history. Clear it
in one of these ways:

1. Fix the data (merge the duplicate people, §6g; reactivate the person; or
   correct the row), then re-run `import_archive_stays`.
2. A **create** stay only: land it by hand as a `PastStay` with `legacy_id`
   set to `archive-stay-<Id>`, where `<Id>` is the **highest** `Id` in the id
   group the report names (e.g. `archive-stay-94` for `57/94`).
3. An **enrich** stay: fill the matched `sheet-stay-…` row's dates, amount
   and currency by hand. **Never** add an `archive-stay-<Id>` row for it:
   reconcile would then count the stay as `exists` and pass, while the guest
   shows the stay twice and the sheet stay stays blank.

There is no admin screen for past stays, so use `manage.py shell` for 2 and 3.
Reconcile checks that a stay has landed, not its values: whatever is entered
by hand is taken as given.

Any other gap is a **blocker**. Track it down before proceeding.

### Rate rule overlap resolution

Legacy had no rate-precedence concept: its per-night lookup was an unordered
`SELECT TOP 1` (`sp_get_quote_weeks_price`) / `FirstOrDefault` over an
unordered `DISTINCT` (`ResService.cs`), so the winner among overlapping
`VillaSeasonRate` rows was formally arbitrary (de-facto lowest ID via the
clustered index). The new schema forbids within-plan overlap outright
(the `rateperiod_no_overlap` / `rateband_bands_no_overlap` EXCLUDE
constraints), so `RateBandLoader` resolves overlaps at load time in two
stages (BUG-016):

Since **GAP-110** the unit of resolution is the **regime plan** — one
`(villa, currency)` bucket, `villa:<VillaId>:<CODE>` — not the legacy season:
rows from every season of a villa that resolves to the same currency trim and
resolve *together* (a season boundary is just another shared boundary; a
cross-season overlap is a conflict like any other, same precedence), while
different villas and different currencies never touch. Each row resolves to
its plan through the **season's** currency (the same `CurrencyId` →
`VillaCurrencyId` → settings → EUR chain `RatePlanLoader` grouped by), never
the row's own `CurrencyId`, so a NULL-currency row lands where its season's
plan went. Rows on soft-deleted seasons or villas have no regime and are
excluded by the query.

**Stage 1 — pre-normalisation** (`resolve_rate_band_overlaps`, per regime
plan, pure on the row dicts):

- **Junk pre-filter** — rows `transform()` would skip (junk dates, no price
  and not POA) are excluded up front so they can neither trim nor be trimmed;
  exact duplicates sharing a discriminator are dropped (dirty-input guard for
  the flattener's duplicate-precedence `ValueError`).
- **Boundary trim** — legacy stored checkout-style contiguous bands (the next
  band starts on the day the previous one ends) but looked them up
  inclusively. The new model is inclusive on both ends, so the earlier row's
  end is trimmed back one day when a party-overlapping sibling starts on it.

**Stage 2 — conflict resolution** (`_load_rows`, via the shared
`pricing.services.flattening.flatten_rate_grid` — the same implementation
projection, carryover and the period backfill use):

- Runs **after** `_row_to_band`'s capacity clamp, so party brackets are
  concrete integers (NULL `PartySize` → `[1, capacity]`, open-topped
  occupancy gaps clamped) before precedence applies.
- Precedence is `(not approved, id, disc)`: `IsApprove = 1` rows claim space
  before unapproved drafts (67 such pairs in the 24-Apr-2025 dump), then the
  earliest legacy ID wins — matching legacy's de-facto behaviour. `disc` is
  the unique per-row discriminator (`_legacy_id`), breaking OccId/ID
  numeric collisions.
- **Split, not clip** — a losing row keeps *every* (date × party) cell no
  winner covers; each surviving fragment becomes one `RateBand`.

The flattener's disjoint output *is* the plan's **`RatePeriod`** date axis
(GAP-056): each flat period is created directly
(`legacy_id = "{plan}:p{i}"`), and a source surviving in more than one cell
is **fragmented** — the bare `legacy_id` goes to its first fragment in
`(period date_from, min_party)` order, later ones get a `#seg{n}` suffix. So
one legacy row now maps to **one or more** bands (was: at most one).

**Behaviour deltas vs the pre-BUG-016 loader** (the clip-only resolver):

- (a) An interior collision (winner strictly inside the loser's span)
  **splits** the loser, keeping BOTH sides — the old code clipped to the
  larger side and discarded the smaller.
- (b) **Single-day remainders persist** as single-day periods — the old
  strict `<` remainder rule dropped them.
- (c) A party-clipped loser keeps **ALL** surviving brackets (e.g. winner
  `(3,3)` vs loser `(1,cap)` → both `(1,2)` and `(4,cap)` persist) — the old
  transform picked only the first surviving interval.
- (d) Conflict resolution now runs **after** the capacity clamp, so rows the
  clamp makes party-disjoint (e.g. `(10,10)` vs `(1,NULL)` on a cap-8 villa)
  no longer date-clip each other.
- (e) For party-clipped rows the bare `legacy_id` attaches to the **lowest**
  surviving bracket (fragment order is `(date_from, min_party)`) — the old
  code kept the highest. Pure date-split `#seg` numbering is unchanged
  (date order, n ≥ 1).
- (f) Row counts shift accordingly — recalibrate the reconcile
  `expected_gap` at the next legacy dry-run.

Consequences:

- Resolution is a function of a regime's whole row set, so every pass is a
  full reload (the table is small).
- Each run is a **full replace**: all legacy-loaded bands + periods are
  purged, then the flattened grid is inserted. Inserting into an empty legacy
  footprint means re-runs can never collide with the previous run's spans
  under the EXCLUDE constraints, so a re-run always converges in one pass
  (the report shows `created=N`, not `updated=N`). UI-created rows
  (`legacy_id IS NULL`) are never touched.
- Dropped rows (fully shadowed) and trimmed boundary days mean quoted prices
  can shift versus legacy for the seasons that had genuinely conflicting
  prices — previously the winner was the highest `ID % 65535` stamp under
  the old per-priority EXCLUDE constraint, and arbitrary in legacy itself.
- The loader logs one summary event per run:
  `data_migration.rate_rule_overlaps_resolved` with `trimmed` / `dropped`
  (pre-normalisation) / `shadowed_dropped` / `party_clipped` (flattener) /
  `purged` / `periods_created` / `rule_fragments` counters. The pre-BUG-016
  first-run numbers (2281 trimmed / 389 dropped on the 24-Apr-2025 dump) are
  no longer directly comparable — the split-not-clip policy reclassifies
  many former drops as fragments.

### Occupancy-band pricing (BUG-013)

Legacy priced a `VillaSeasonRate` two ways. A simple rate carried one
`PartySize` + price. An **occupancy** rate (`IsOccupationPrice = 1`) was a
parent whose child **`VillaOccupencyPrice`** rows carried
`(OccupencyFrom, OccupencyTo, OccupencyPrice)` party bands (e.g. 2–4 → €500/wk,
5–6 → €700/wk); legacy quoted the band matching `From ≤ guests ≤ To`, and fell
back to the parent's `WeeklyPrice / 7` when no band matched. The original
migration read `VillaSeasonRate` alone and **silently dropped every band**.

`RateBandLoader` now recovers them (no separate loader — all of a plan's rules
must be made jointly overlap-free under the one EXCLUDE constraint):

- The `legacy_query` **LEFT JOINs `VillaOccupencyPrice`** onto its parent (every
  parent column `r.`-qualified — both tables have an `Id`/`ID` PK). The child
  table has no `DeletedAt`, so the join is on `VillaSeasonRateId` alone.
- `_prepare_occupancy_rows` expands each `IsOccupationPrice` parent with ≥1
  **valid** band into: one **band rule** per band (party range +
  `OccupencyPrice` as the weekly rate) **plus** one **base-weekly fallback
  rule** per party gap the bands leave uncovered (below the lowest band, between
  bands, above the highest — clamped to capacity). So a guest count matching no
  band still gets the legacy base-weekly quote (full parity).
- **`IsOccupationPrice` gates expansion.** A rate not flagged occupancy keeps
  its flat price even if stray `VillaOccupencyPrice` rows exist — legacy never
  reads them. A flagged parent with no children is a plain base-weekly rate.
- **Invalid bands are dropped, not coerced:** null/≤0 bounds, `From > To`, or a
  null/0 price. Such a band priced nobody in legacy, so its party range falls to
  the base-weekly fallback (a null bound would also crash the resolver).
- **`legacy_id` namespacing:** band rules are keyed `occ-{OccId}` and fallbacks
  `occ-fb-{parent}-{k}` (stamped by `_prepare_occupancy_rows` and carried
  through `_load_rows`), because
  `VillaOccupencyPrice.Id` and `VillaSeasonRate.ID` are independent sequences
  that would otherwise clobber on upsert. The full-replace purge
  (`legacy_id IS NOT NULL`) covers both, so idempotency holds.
- Band nightly rates are **not stored** — the engine's `rule_nightly` derives
  `weekly / 7` (HALF_EVEN) identically at quote time.

**Cutover verification items:**

1. **Recalibrate the RateRule `expected_gap`** (see the reconcile table above) —
   the count now spans parents + occupancy children and can only be derived
   against the live dump.
2. **Band-vs-simple precedence edge.** If a season has both an occupancy-banded
   parent and a *separate* simple `VillaSeasonRate` with overlapping dates and
   party ranges, the shared flattener orders them by
   `(not approved, id, disc)` — where a band's `id` is its `OccId` and a simple
   row's is its `VillaSeasonRate.ID`, two unrelated sequences. Which wins (and
   thus whether the recovered band survives or is split/dropped) is
   deterministic but arbitrary. Legacy's own per-night `TOP 1` was unordered
   here too, so there is no single parity answer — but if a spot-check shows
   real bands being lost this way, give band rows explicit precedence (an
   `is_occ` sort key ahead of `id`).
3. **Recalibrate the villa-level `RatePlan` check** (GAP-110, `expected_gap`
   placeholder `0`): the legacy side is distinct live villas with ≥1 live
   priced rate row, the loaded side villas owning a `villa:`-keyed plan with
   ≥1 legacy period. Any gap is a villa the loader could not resolve (no
   `Property`, no currency) — itemise before pinning.
4. **Night-parity residue** (GAP-110): the per-villa night-set section is
   expected at `0` villas. A non-zero residue must be itemised per villa
   (villas with no `Property`; negative-price junk rows) and either fixed in
   the loader or pinned as an explained loss — never waved through.
5. **Legacy-quote sample on the overlap villas** (GAP-110): 37 villas had
   cross-season same-party overlaps in the 24-Apr-2025 dump (298 pairs), which
   the regroup now resolves *across* seasons by `(not approved, id, disc)`.
   Spot-check that the resolved winner reproduces the legacy quote on a
   sample of `VillaQuotationMaster` rows for those villas; a systematic miss
   means the cross-season precedence needs an `is_occ`/season sort key, not
   a per-villa patch.
6. **A staff-made plan in a loader regime blocks the villa's re-load.** Two
   invariants bite, and they need different remedies:
   - `rateplan_one_active_per_regime` — at most one *active* `RatePlan` per
     `(property, currency, price_basis)`. A staff-made **active GROSS** plan
     in a currency the loader mints for that villa makes `rate_plan` fail
     that villa's `(villa, currency)` group (its own savepoint; the other
     villas still load; loaded plans are always GROSS — SMELL-021).
     Remedy: **deactivate** the staff plan first.
   - `rateperiod_no_overlap` — ungated by `is_active`, so deactivating is
     **not** enough if the staff plan's periods overlap the legacy dates:
     `RateBandLoader` writes every villa inside **one outer
     `transaction.atomic()` with no per-plan savepoint**, so a single
     overlapping staff period rolls back the **entire** `rate_rule` load and
     `loadlegacy` exits non-zero. "Merging" the staff periods onto the loaded
     plan is equally unsafe — merged periods keep `legacy_id NULL`, survive
     the full-replace purge, and collide on the next run. Remedy: **delete**
     the staff plan's overlapping periods (or the whole staff plan) before
     the re-run.
   Nothing in the loader retires or deletes staff rows. Migration
   `pricing/0011` handles the one loader-made case: it **deactivates
   pre-regroup season-keyed loader plans** (`legacy_id` set but not
   `villa:…`) so the unique-active constraint can land on a DB loaded before
   the regroup; the `rate_plan` loader's own targeted sweep
   (`RatePlan.objects.filter(legacy_id__isnull=False).exclude(legacy_id__startswith="villa:").delete()`,
   cascading their legacy periods/bands) then removes them on the next run —
   the bands/periods full-replace purge never deletes plans. **Known
   leftover:** a stale `villa:<id>:<CODE>` plan whose villa re-resolved to
   another currency, or lost all its priced rows, is *not* swept — it
   survives as an active, periodless plan (harmless to pricing, visible in
   the workbench picker); deactivate or delete it by hand. This only arises on
   an in-place re-run, which is unsupported (one-shot, BUG-029) — a fresh
   load never meets it.

## 6. Late writes

There is no delta mode (`--since` was retired in BUG-029): `loadlegacy --all`
is a one-shot into a fresh DB. If legacy took writes after the freeze in
step 1, or a run failed or was aborted, drop and recreate the Postgres DB,
`migrate`, retake the dump (§2–§3), reload with `loadlegacy --all` and re-run
`reconcile_legacy` (§5) — the same steps as [Rolling back](#rolling-back).

## 6b. (Optional) Room-attribute backfill from prose (GAP-064/GAP-065/GAP-066)

Room amenity facts live in `website_description` prose in the legacy book
(loaded byte-for-byte by `RoomLoader`) and crammed into the free-text
placement string preserved as `placement_note` (GAP-065 — e.g. "First floor -
King, hairdryer"). After the rooms load, an optional positives-only keyword
pass over both sources can enrich the structured GAP-064 columns:

```bash
uv run python manage.py backfill_room_attrs --dry-run   # inspect counts first
uv run python manage.py backfill_room_attrs
```

It creates `RoomAttributeAssignment` rows for confident keyword matches,
fills `ensuite_type` from explicit "en-suite shower/bath" phrasing (only when
currently unknown), re-homes a hand-typed bed size (King / Super-king /
Emperor) onto `RoomBeds.double_size` (GAP-066 — only for a room with a double
bed and no curated size yet), and first re-invokes `sync_room_attributes()` so
the catalog's `implies_property_feature` links attach now that Features exist.
It never infers absence, never removes assignments, never overwrites curator
data — safe to re-run any time. There is no
`reconcile_legacy` row for this: no legacy table exists to compare against;
the command's per-slug and per-size counts are the reconcile signal. (Placement itself
DOES have a reconcile row — "Room placement (GAP-065)" gates that every
legacy `PlacementId` landed with a preserved `placement_note`.)

## 6c. (Optional) Derive property features from room attributes (GAP-067)

Once §6b has attached `RoomAttributeAssignment` rows (and the catalog's
`implies_property_feature` links are live), a room attribute that implies a
property feature should surface that feature on the parent property. The room
save-path does this live, but the backfill writes assignments in bulk without
going through it, so run the sweep once — **after** the feature loader and the
room-attribute backfill:

```bash
uv run python manage.py recompute_derived_features --dry-run   # inspect counts first
uv run python manage.py recompute_derived_features
```

It reconciles each property's `is_derived=True` `PropertyFeature` links to the
union of `implies_property_feature` across its rooms — adding implied features,
removing no-longer-implied ones, and never touching manually curated links.
Idempotent, so it is safe to re-run. `--dry-run` runs the
whole sweep inside a rolled-back transaction and reports the counts a real run
would apply. There is no `reconcile_legacy` row: derived links have no legacy
source table to compare against — the command's added/removed counts are the
reconcile signal.

## 6d. Provision the SMTP profile (manual, deliberate)

Legacy `VillaConfigEmail` is **not** loaded (19 of its 20 rows are UAT junk;
secrets shouldn't ride a data migration). Create the single production
`comms.SmtpProfile` (SYSTEM scope) by hand at cutover — the real legacy row
is the office365 profile for info@villacollective.com; fetch the current
credentials from the ops secret store, not from the dump.

## 6e. Unfuse `villa_info` after GAP-091 (only for DBs loaded before 2026-09)

> _(Historical — an in-place named-loader repair of an already-loaded staging
> DB. The one-shot cutover loads a fresh DB and never needs it; `--since`,
> referenced below, was retired in BUG-029.)_

Before GAP-091 the property loader fused `VillaMaster.FeatureDescription`
(the legacy Features page's "Other information description") and
`VillaMaster.RoomDescription` (the bedrooms blurb) into one `villa_info`
description with a blank-line join. Migration `properties.0007` renames those
rows to `other_information` **unchanged** — the join is not reversible by
string splitting. A fresh cutover load (§4) never sees this; a DB that was
loaded earlier (staging) needs one property-loader re-run, **immediately after
the deploy and before staff edit anything**, and **without `--since`** (the
fused rows belong to villas whose legacy `UpdatedAt` has not moved):

```bash
uv run python manage.py loadlegacy property
uv run python manage.py zoho_backfill --kinds villa   # loaders run under suppress_zoho_push()
```

**Blast radius.** `property` is a full upsert from the dump, not a
descriptions-only fix: it rewrites `Property`, `PropertyLocation`,
`PropertyCapacity`, `PropertySettings` and every description section whose
legacy column is non-blank (at the time: `overview`, `house_rules`,
`further_info`, `web_description`, `location`, and then `other_information` /
`rooms` — GAP-090 has since replaced the last three with the sub/para block
set, see [§6i](#6i-split-the-fused-website-blocks-after-gap-090-only-for-dbs-loaded-before-2026-09-20)) for every villa. Staff edits to any of those made after the earlier load are
overwritten — the same contract as any cutover-window delta load, which is
why it runs before staff get the keys. The Zoho re-push is suppressed inside
the loader (base.py), hence the backfill line.

What the re-run does to the renamed row: `FeatureDescription` non-blank →
rewritten in place as `other_information` with `<Id>-other_information`
provenance. `FeatureDescription` blank → the `<Id>-villa_info` row is dropped
(audit tombstone + `data_migration.fused_description_dropped` log line) **only
while its body still equals the old join of the current legacy columns**; a
row that no longer matches (staff rewrote it, or legacy changed since) is kept
and logged as `data_migration.fused_description_kept` — grep the run's log for
that event and clear those by hand. Rows staff typed after cutover carry no
`legacy_id` and are never touched. This is a targeted one-off keyed on the
`-villa_info` provenance, not a stale-row sweep: a description whose legacy
column later goes blank is left in place, as it always was for every section.
Idempotent.

Two related one-offs after the feature loaders run:

- The "Other information" tags are `Feature` rows in the `other-information`
  `FeatureCategory` (legacy category Code 60 / Id 8). Legacy carries one live
  junk row there — `304 Dev Feature` — which WILL surface as an assignable tag.
  Deactivate it in the Tags admin (`is_active=false`); nothing in code filters it.
- `298 Sea View` is mapped to eight legacy categories; `FeatureLoader` files it
  under the first (`Included Features`), not under other-information. Expected.

## 6f. Re-stamp `PropertyFinance.legacy_id` after GAP-107 (only for DBs loaded before 2026-09)

> _(Historical — an in-place named-loader repair of an already-loaded staging
> DB. The one-shot cutover loads a fresh DB and never needs it; `--since`,
> referenced below, was retired in BUG-029.)_

Migration `properties.0008` adds `PropertyFinance.legacy_id` as schema only:
on a DB loaded earlier (staging) every row stays `NULL`, so the §5
`VillaFinance` check reads `loaded = 0` and BLOCKERs until the per-villa
pass re-stamps its rows. A fresh cutover load (§4) never sees this. Run once,
**without `--since`** (the stamp is not a legacy change):

```bash
uv run python manage.py loadlegacy property_finance
```

**Blast radius.** `property_finance` upserts every migrated villa's own
finance row from the dump (staff edits since the earlier load are
overwritten — the same contract as any delta load) and leaves the GAP-070
fallback rows alone (`create-only`, so they keep their `NULL` marker).
Idempotent.

## 6g. Post-load Person merges (BUG-030 §18)

The legacy data holds the same human twice. The loader keeps both rows
(the keys are what `reconcile_legacy` counts), so staff fold them by hand
**after §5 has passed** — never before, because a merge hard-deletes the
source Person and its `legacy_id` with it.

Merge each source into its survivor with `POST /contacts/{source_id}:merge`
(admin-only; body `{"target_contact_id": <survivor_id>}`). `Person.merge`
repoints every FK (bookings, enquiries, quotations, preferences, property
assignments, channels) before deleting the source.

**Find the candidates on the loaded DB, don't work from a pinned list.** The
three pairs this section used to name (`client-4` → `client-1`, contact `1` →
`client-5`, contact `232` → `client-19`) were derived on the 24-Apr-2025 dump
and **none of those client ids exists on ResProd** — the lowest
`VillaClientDetails.Id` is 2. Re-derive instead:

```python
# uv run python manage.py shell
from django.db.models import Count
from accounts.models import PersonEmail

dupes = (
    PersonEmail.objects.exclude(email="")
    .values("email")
    .annotate(n=Count("contact_id", distinct=True))
    .filter(n__gt=1)
)
for row in dupes:
    people = PersonEmail.objects.filter(email=row["email"]).select_related("contact")
    print(row["n"], row["email"], [(p.contact_id, p.contact.legacy_id, p.contact.full_name) for p in people])
```

On ResProd (13-Aug-2026, after both sheet imports) that is **81** addresses
carried by more than one Person: 35 sheet-only (`sheet-person-…` on both
sides — the spreadsheet's own repeats), 33 a `client-` Person against a sheet
Person, 6 a `client-` against a `VillaContact` Person, 5 a contact against a
sheet Person, and 2 spanning all three slices.

Two rules for working the list:

- **An e-mail match is a candidate, not proof.** Shared and role addresses
  (`info@…`, an agency's front desk, a villa manager's own address on their
  owners' records) legitimately sit on several real people — they are part of
  why the 184 unnamed clients in [§5](#5-verify-with-reconcile_legacy) have no
  identity to import. Confirm the names and the linked
  bookings/enquiries agree before merging; when in doubt, leave both.
- **Prefer the `client-` Person as the survivor** where the pair has one:
  bookings, quotations and guest preferences reference it. A sheet Person is
  the next best survivor, then a `VillaContact` one. Merging *into* a sheet
  Person is safe but loses the `legacy_id` that ties the row to the dump.

A `reconcile_legacy` re-run after the merges will move the person counts, and
only those (plus, possibly, the GAP-112 invariant — last bullet) — each merge
deletes the source Person and its `legacy_id` with it,
which is exactly why this runs **after** §5 has passed:

- `Person (owner/agent)` gap **+1 per merged-away contact** Person.
- `Person (client)` gap **+1 per merged-away `client-`** Person.
- `PersonEmail` / `PersonPhone` gap **+ the channels each merged-away Person
  owned**, which now sit on a Person outside that check's counted slice (a
  shared address folds into the survivor's row).
- Sheet-only merges move no count: `reconcile_legacy` leaves every `sheet-` row
  out of its counts. They can still trip the GAP-112 invariant below.
- `Quotation on unknown client with a relinkable enquiry` goes **non-zero** when
  a merge leaves a formerly shared address with a single holder — that
  enquiry is now resolvable. Re-run `relink_enquiry_customers` (idempotent)
  rather than accept the drift.

Record the merges you ran; the numbers above are the only sanctioned drift
between a passing §5 and a later reconcile.

## 6h. Phone numbers ending `.00` (only for DBs loaded before 2026-09-20)

> _(Historical — the defect is fixed in the parser. A fresh cutover load never
> sees it.)_

`Enquiries - FINAL.xlsx` writes some phone cells as the literal **string**
`+44 7985414214.00` (openpyxl type `str`, format General), so the reader's
integral-float coercion never fires. Before GAP-118, `to_e164` could not parse
that and returned it unchanged, leaving 713 of 2 099 `PersonPhone` rows with a
`.0`/`.00` tail (691 on `sheet-person-…` people, 22 on legacy `client-…` ones).

`reservations.phone.to_e164` now strips a trailing `\.0+` before parsing, and
only rewrites the value when the stripped form is a **valid** number — an
unparseable string still passes through verbatim. The tail must be the
string's **only** dot, so a dot-separated French number (`04.93.12.34.00`)
is left alone. That covers `import_enquiry_sheet` and `legacy_phone` in one
place.

Two residues survive a fresh load, both by design: a number whose stripped
form still fails validation keeps its tail (`legacy_phone("0030",
"12345.00")` → `+30 12345.00`, BUG-030 §17 — the country is worth more than
the tail), and a dot-separated number is never touched.

**An already-loaded DB is not repaired by re-running the imports**, and the
residue is not only `PersonPhone`:

- `import_enquiry_sheet` only writes a phone to a person who has **none**
  (`if phone and not person.phones.exists() and channels_writable(...)`), so
  a person already carrying a `.00` number is skipped and
  `reconcile_primary_phone` is never reached. (Had it been reached it would
  have corrected the row in place — it updates the PRIMARY row, it does not
  add a sibling.)
- `Enquiry.phone` is written from the same cell inside a
  `get_or_create(defaults=…)`, so existing enquiry rows keep their tail too.

Dev and staging get clean numbers on their next fresh rebuild. Nothing to run
at cutover.

## 6i. Split the fused website blocks after GAP-090 (only for DBs loaded before 2026-09-20)

> _(Historical — an in-place named-loader repair of an already-loaded staging
> DB. The one-shot cutover loads a fresh DB and never needs it.)_

Before GAP-090 the property loader fused each legacy sub/para pair with a
blank-line join — `WebDesc1+WebDesc2` into one `web_description` row,
`Location1+Location2` into one `location` row — and never read
`Interior1/2` or `Exterior1/2` at all. Migration `properties.0010` remaps the
loaded rows **unchanged** (`web_description` → `web_des_1`, `location` →
`location_sub`, `further_info` → `internal_notes`); no string split can undo
the join, so only a loader re-run produces the real halves. A fresh cutover
load (§4) never sees this; a DB loaded earlier (staging) needs one
property-loader re-run, **immediately after the deploy and before staff edit
anything**:

```bash
uv run python manage.py loadlegacy property
uv run python manage.py zoho_backfill --kinds villa   # loaders run under suppress_zoho_push()
```

**Blast radius.** The same as §6e — `property` is a full upsert, so
`Property`, `PropertyLocation`, `PropertyCapacity`, `PropertySettings` and
every description section whose legacy column is non-blank are rewritten for
every villa, and staff edits made since the earlier load are lost. **With one
exception: `internal_notes` is never overwritten.** It has been an editable
staff surface since 2026-08-12 and migration 0010 folded the retired
`further_info` bodies into the same rows, so the loader writes that section
create-only; a kept row is left verbatim and logged as
`data_migration.internal_notes_kept`. Its `legacy_id` is still re-stamped, so
the row counts as loaded in §5.

What the re-run does to each parked row:

- **Part 1 non-blank** (the normal case) → the sub row is rewritten in place
  with the true part-1 text and `<Id>-<section>` provenance, and the para row
  is created alongside it.
- **Part 1 blank, part 2 set** → the old join wrote part 2's text into what is
  now the *sub* slot, and the re-run cannot claim that row. It is dropped
  (`data_migration.fused_block_dropped`) **only while its body still equals
  the old join of the current legacy columns**; a row that no longer matches
  is kept and logged as `data_migration.fused_block_kept` — grep the run's log
  for that event and clear those by hand. On ResProd this is the handful of
  villas where `Location2` is set but `Location1` is not (347 vs 346).
- **Interior / Exterior** → straight creates. They had no pre-GAP-090 section,
  so nothing is parked and nothing is dropped.

**The photo captions stay.** `PropertyImageLoader` reads the same four
`Interior*`/`Exterior*` columns into `PropertyImage.description`, and that is
deliberate, not a double import: the `IsInterior1/2`/`IsExterior1/2` flags on
`VillaPropertyImages` mark which photo sits beside which block, and 1 572
flagged images carry no `Description` of their own. Removing either surface
would blank the other's copy.

**Until the re-run, §5 reads the old total.** The `PropertyDescription` check
now expects **3 200** rows (13 sections/villa); a DB still holding fused rows
reports around 1 049 and a large gap. That is expected before this step and a
blocker after it.

**Per-room `WebsiteDescription` is deliberately not surfaced.** GAP-092
retired the room-level field from the API and the UI — legacy
`VillaRooms.WebsiteDescription` is an attribute list (`"Double/Twin, En
suite, Bath with shower, Air conditioning, Sea view"`, 2 668 of 2 714 rows,
max 148 chars), not prose, and the property-level `rooms` blurb
(`VillaMaster.RoomDescription`) is the real bedrooms copy. `RoomLoader` still
writes the column, because `backfill_room_attrs` (§6b) keyword-mines it for
room facets. An accepted, documented non-loss: no staff surface reads it.
One consequence: with no surface left to edit the source text, a
`backfill_room_attrs` re-run after go-live re-asserts any facet or amenity
link staff have since removed from a room whose imported list names it (the
command is positives-only). Treat the backfill as a cutover step, not a
routine job.

Idempotent.

## 7. England → GB merge (retired — BUG-030 §6)

No longer a cutover step. The legacy "England" row (`VillaCountry` 24,
ShortName1 `UK`, deleted) used to load as a bogus `Country(iso2="UK")` that
staff then merged into `GB` with `merge_country`. `CountryLoader` now
validates ISO codes (`UK` → `GB`), so row 24 resolves to GB, is skipped
(row 6 "United Kingdom" holds the GB seed's `legacy_id`), and every
`CountryId = 24` consumer (regions, clients) lands on GB through
`country_for_legacy_id` (`loaders/_util.py`, `LEGACY_COUNTRY_ALIASES`).
`merge_country` stays as a generic staff tool; nothing in the runbook
calls it.

## 8. Image files

The DB rows are already in place (~13 000 `properties/legacy/<file>` keys
with no backing binaries). Upload the binaries with:

```bash
uv run python manage.py import_legacy_images --source <PropertyImages dir> --dry-run
uv run python manage.py import_legacy_images --source <PropertyImages dir>
```

`--source` is the exported legacy `PropertyImages/` directory (per-villa-id
subfolders); the command reconstructs each nested source path from
`property.legacy_id` and uploads to the row's existing flat key. Idempotent;
missing-at-source files are the documented expected-loss bucket.

**Ordering:** the import must run into the `production/` prefix **before**
the prod deploy that flips storage to S3 — `settings/production.py` on main
already selects S3, so any prod push of main carries the flip. Full runbook
(env vars, IAM prereqs, staging reset):
`django_res_design/todo/gap-012-s3-image-hosting.md` §Cutover runbook.

## 9. Cut DNS / app config

Switch the Villa Collective frontend (and any integrations) to the new
Django backend's base URL. Smoke-test:

- `/api/v1/quotations` returns only real quotations. The viewset still
  excludes `legacy_id__startswith="booking-"`; since GAP-089 unregistered the
  booking loader nothing mints those any more, so the exclusion should now be
  a no-op — a non-empty result from
  `Quotation.objects.filter(legacy_id__startswith="booking-")` means a booking
  loader ran (the `Booking with legacy_id` invariant in
  [§5](#5-verify-with-reconcile_legacy) catches the same thing).
- `/api/v1/countries` returns the canonical ISO-3166 list, including `GB`.
- A property card shows a price — i.e.
  [§4a](#4a-pricing-summaries--automatic-with-a-manual-fallback)'s rebuild
  landed.
- A staff user can log in and read a property's full detail page.

## 10. Retire the legacy container

After 24–48 hours of clean operation:

```bash
cd ResSystem && docker compose down -v
```

Archive the dump (`NewResSystem_YYYYMonDD.bak`) to the ops data-retention store
(typically S3). Keep the `data_migration/` Python package in the
repo indefinitely — the loaders document the legacy schema and remain the
authoritative migration record.

## Rolling back

If something blocks the cutover after step 4, the new Postgres DB can be
re-seeded any time by:

1. `dropdb villacollective && createdb villacollective`
2. `uv run python manage.py migrate`
3. `uv run python manage.py loadlegacy --all`

The load is a one-shot: always go through the drop / recreate / `migrate` /
reload above, never an in-place second `loadlegacy --all` — the command
refuses a DB that already holds legacy-loaded rows (there is no `--force`).
Named loaders (`loadlegacy <name>`) are not guarded; they are a debugging aid,
not a production path.
