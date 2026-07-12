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
  migrated.
- A staff user authorised to run management commands on the production
  cluster.
- `LEGACY_DATABASE_URL=mssql://sa:<pw>@<host>:<port>/NewResSystem`
  exported in the shell.

## 1. Freeze legacy writes

Per ops procedure — typically by switching the legacy app to maintenance
mode. Capture the freeze timestamp; this becomes `--since` if a follow-up
delta load is needed.

## 2. Take the final legacy dump

The current convention is `live-db-YYYY-MM-DD.sql` (UTF-16 LE). Copy it
into the local `ResSystem/Database/` directory.

## 3. Reseed `res-db` from the final dump

```bash
.claude-tmp/drop-and-reseed.sh
```

Wait for the script to report `Restore complete`. Sanity-check that
`SELECT COUNT(*) FROM VillaMaster` returns the expected number of
properties.

## 4. Run every loader

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

Expect this to finish in ~2 minutes on the live snapshot. Watch for any
non-zero `errors` column in the per-loader summary; investigate before
proceeding. Since 2026-07-05 the command is strict and crash-isolated: a
loader that raises no longer aborts the run (its failure lands in the
summary as `<loader crashed>`, remaining loaders still run, the sequence
sync still happens) and the command **exits non-zero if any loader crashed
or reported errors** — so "step passes iff exit 0" now holds here too.

Two loader behaviours to know about (both 2026-07-05, see `DRYRUN_LOG.md`):

- **Legacy `IsDefault*` flag resolution is DEFERRED** (separate finance
  investigation — GAP-073 owner decision 2026-07-06). Legacy overrode a
  flagged row's stored column with the `VillaConfigPropertyDefault` value at
  read time (min-nights 7, EUR currency, 20% commission, payment-schedule and
  security-deposit defaults); reproducing that — plus the related
  commission/deposit type-code re-key (`10=Percentage / 20=Fixed`) and the
  VillaCurrency duplicate-code resolver — was built on `feat/legacy-loader`
  but NOT landed here, pending confirmation that GAP-070's `PropertyDefaults`
  snapshot doesn't already cover it. Until then finance/settings values load
  from the stored VillaMaster columns as before.
- **`availability_block`** ports future non-available legacy calendar runs
  into `BookingHold(reason=MANUAL)` rows (see the reconcile table below).
  Like `rate_rule` it ignores `--since` and full-replaces its own
  `avail-*` slice per run.

## 4b. Capture external IDs into `SyncRecord` (Zoho)

This step **captures** the external ids Zoho already issued against legacy
rows into `integrations.SyncRecord`, while the legacy DB is still readable.
The `syncrecord_zoho` loader runs as part of `loadlegacy --all` in step 4,
so there is nothing extra to run here — this step is the verification.

> **Live-schema reality (2026-07-05 dry run):** only `VillaContact`,
> `VillaEnquire` and `VillaMaster` actually carry a `ZohoId` column in the
> prod dump — `VillaQuotationMaster` and `VillaBooking` do **not** (the
> five-table list below was aspirational). The loader and the reconcile
> section probe `INFORMATION_SCHEMA` per table and skip/annotate absent
> columns, so a schema-vintage difference can no longer crash the run.
> Known accepted gap: `VillaMaster` continuity expects gap **1** — legacy
> rows 88 (*Temenos Villa Templos*) and 339 (*Temenos Villa Kioni*) are two
> **distinct** villas that share one `ZohoId` (`577032000002128026`), a
> source-side error in Zoho, not duplicate Property records. **Product
> decision 2026-07-06: ACCEPT.** Both villas migrate; the SyncRecord attaches
> to the lower legacy Id (88, forced by `ORDER BY Id` in the loader query so
> it is reproducible), and the shared `ZohoId` is flagged to the CRM owner for
> a source-side fix. The gap stays **1** until Zoho is corrected — no property
> merge is warranted.

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
  (`VillaMaster`, `VillaContact`, `VillaEnquire`, `VillaQuotationMaster`,
  `VillaBooking`), the count of backfilled `SyncRecord(provider=ZOHO_CRM)` rows
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
  justification. (The check compares counts, not values; a full `loadlegacy
  --all` refreshes every `external_id`, but a value drifted on a delta-only
  `--since` pass whose `UpdatedAt` did not advance is not caught here.)
- **WordPress surface** (informational only): legacy `VillaBooking.BookingUrl`
  and `VillaSyncDetail` volume. The WordPress backfill is **not built yet** —
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
`reference` (all organic), and the imported Enquiry format (`E-{Id:06d}` /
numeric `EnquiryNo`) is disjoint from the organic `E-{year}-{n}` shape, so an
organic reference can never collide with an imported one.

## 4d. Customers load straight to `Person` (GAP-045)

`VillaClientDetails` no longer loads to a `reservations.Guest` — `ClientLoader`
writes a unified `accounts.Person` **directly**, keyed `legacy_id="client-{Id}"`
with `kind=CUSTOMER`, reconciling each row's single legacy email/phone onto a
PRIMARY `PersonEmail`/`PersonPhone` child in place (idempotent on re-run). The
downstream loaders (quotation, booking, preference) resolve their customer FK
through `person_for_client("{Id}")` → that same `client-{Id}` Person; the rare
no-name client `ClientLoader` skips falls back to the `unknown_client` sentinel
rather than dropping the referencing row.

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
slice of `Person` (`expected_gap=1`, the no-name row), and the `VillaContact`
owner/agent check excludes that slice — see the two `Person (...)` rows in the
table below.

## 4e. Free-text companies fold into `Organisation` (GAP-046)

`VillaContact.Company` is no longer copied into a free-text `Person.company`
column. `ContactLoader` routes each non-blank company string through
`accounts.services.organisations.organisation_for_company_name`, which
get-or-creates a deduped `Organisation(org_type=agency)` keyed on a content hash
of the **case/whitespace-normalised** name (`dedup_key`, never `legacy_id`) and
links the contact via `Person.agency`. A blank company → `None` → null agency.
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
  most recent **on/before `booking.date_from`** (pinned so delta re-runs are
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

## 5. Verify with `reconcile_legacy`

```bash
uv run python manage.py reconcile_legacy
```

The command now enforces this itself: it prints an `expected`/`status`
column and **exits non-zero** if any row's `gap != expected_gap`, so this
step passes iff the command succeeds — no manual cross-reference needed.

The expected-gap numbers live in `reconcile_legacy.py` (`_CHECKS`), which is
their single source of truth. The table below is a human-readable mirror;
if the live dump legitimately shifts a number, change it in the code (that
is where the dry-run calibration happens), not just here.

| Source table              | Expected gap | Reason |
|---------------------------|--------------|--------|
| `VillaCollectionsMappings`| 308          | Legacy has duplicate mapping rows for the same (collection, property); collapsed. |
| `VillaFinance`            | 1236 *(placeholder)* | **Recalibrate at the first post-GAP-070 dry-run.** 1236 was exact while loaded matched the `VillaId IS NOT NULL` universe 1:1 (413 contact-default template rows + 676 parent-child override rows, neither with a per-villa home). The GAP-070 owner-contact fallback now also *creates* a `PropertyFinance` row for each financeless villa with a live OWNER assignment, so the true gap is 1236 minus that fallback count — only derivable against the live dump. |
| `VillaCurrency`           | 4            | Junk rows (`HTFG`/`RUPEE`/`RS`) with zero FK references are skipped. |
| `VillaSeasonRate` (+ `VillaOccupencyPrice`) | 3805 *(calibrated 2026-07-05)* | **BUG-013**: the check counts both `VillaSeasonRate` parents **and** `VillaOccupencyPrice` bands on `IsOccupationPrice` parents. Fully itemised in `reconcile_legacy.py` (balances to zero residual): dominated by 2477 priceless non-POA rows and 985 rows on seasons with no RatePlan; occupancy expansion and flattener fragments net off. Recalibrate on a newer dump — the mix moves with the data. |
| `VillaMaster`             | 1            | One row with empty `Name`. |
| `VillaContactMapping`     | 1            | Composite legacy_id collapse. |
| `VillaClientDetails`      | 1            | One row with neither `FirstName` nor `LastName` (no identity to import). Loads to the `client-` slice of `Person` (GAP-045). |
| `VillaBookingDetails`     | 0 *(confirmed at 2026-07-05 dry-run)* | **GAP-017**: the legacy side already excludes zero-price rows and rows on deleted bookings; the loaded side counts only imported rows (`legacy_id IS NOT NULL`), so staff-created charge lines never skew it. Error/skip rows widen the gap until fixed: no-rate FX rows, unresolvable non-zero `CurrencyId`, conversions quantising to zero, unresolvable bookings — see [4g](#4g-chargeable-extras--bookingchargeitem-gap-017). |
| `VillaAvailability` (future days) | 0 | New `availability_block` loader (2026-07-05): future non-available day rows (statuses 30/40/50/60, `AvailableDate >= today`) coalesce into `BookingHold(reason=MANUAL)` rows; the check compares future day counts to the summed day-span of loaded `avail-*` holds. Both sides move with "today" — run load and reconcile the same day. Skips (unloaded property / range occupied by an imported booking or staff hold) widen the gap; recalibrate against the final dump if non-zero and explained. |

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

**Stage 1 — pre-normalisation** (`resolve_rate_band_overlaps`, per season,
pure on the row dicts):

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

- The loader **ignores `--since`** (and logs a warning if passed) —
  resolution is a function of a season's whole row set, so every pass is a
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

## 6. (Optional) Delta load for late writes

If the freeze in step 1 wasn't perfectly clean, you can run a second pass
restricted to rows updated after the freeze:

```bash
uv run python manage.py loadlegacy --all --since '2026-05-13T17:00:00'
```

Loaders use the legacy `UpdatedAt` column for this filter — a few lookups
without that column will silently ignore the flag. `rate_rule` also ignores
it by design: overlap resolution needs the whole season's row set, so it
always does a full reload (see "Rate rule overlap resolution" above).
`booking_charge_item` likewise ignores it (with a warning) —
`VillaBookingDetails` has no `UpdatedAt`, and the removal sweep needs the
full row set to detect deletions. `property_defaults` **skips entirely** on
`--since` (with a warning): the loader re-applies the legacy
`VillaConfigPropertyDefault` singleton onto `PropertyDefaults` (pk=1 — it
deliberately has no `legacy_id`), and a delta run must not clobber edits
staff made through `PATCH /property-defaults` during the cutover window.

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
data — safe to re-run any time (e.g. after a delta load). There is no
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
Idempotent, so it is safe to re-run after a delta load. `--dry-run` runs the
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

## 7. England → GB merge

After Phase 1.1 added the canonical `GB` row, the legacy "England"
(iso2 `UK`, legacy_id `24`) row is no longer needed. Merge once:

```bash
uv run python manage.py merge_country --from-legacy 24 --to-iso2 GB
```

Output should report `Rewrote N rows and deleted source country.`

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

- `/api/quotations` returns only real quotations (no synthesised
  `legacy_id` starting `booking-`).
- `/api/countries` returns the canonical ISO-3166 list, including `GB`.
- A staff user can log in and read a property's full detail page.

## 10. Retire the legacy container

After 24–48 hours of clean operation:

```bash
cd ResSystem && docker compose down -v
```

Archive `live-db-YYYY-MM-DD.sql` to the ops data-retention store
(typically S3). Keep the `data_migration/` Python package in the
repo indefinitely — the loaders document the legacy schema and remain the
authoritative migration record.

## Rolling back

If something blocks the cutover after step 4, the new Postgres DB can be
re-seeded any time by:

1. `dropdb villacollective && createdb villacollective`
2. `uv run python manage.py migrate`
3. `uv run python manage.py loadlegacy --all`

All loaders are idempotent (upserts keyed on `legacy_id`, or on the
content-type tuple for `syncrecord_zoho`), so re-running from scratch is
safe.
