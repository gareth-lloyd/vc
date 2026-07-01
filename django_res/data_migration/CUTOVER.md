# Legacy → Postgres Cutover Playbook

This is the ops checklist for the final cutover from `ResSystem/` (.NET 7 +
Azure SQL Edge) to the new Django REST API + Postgres backend.

Run end-to-end **after** a green CI on `main` and a confirmed dry run
against a recent dump. The goal is to land every legacy row that has a
schema home in the new system, with zero unexplained gaps in
`reconcile_legacy`.

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

Expect this to finish in ~2 minutes on the live snapshot. Watch for any
non-zero `errors` column in the per-loader summary; investigate before
proceeding.

## 4b. Capture external IDs into `SyncRecord` (Zoho)

This step **captures** the external ids Zoho already issued against legacy
rows into `integrations.SyncRecord`, while the legacy DB is still readable.
The `syncrecord_zoho` loader runs as part of `loadlegacy --all` in step 4,
so there is nothing extra to run here — this step is the verification.

Why it is time-critical even though nothing syncs yet: the legacy DB is the
only home of these ids and it is decommissioned 24–48h after cutover (step
10). These ids are the routing keys for every future push — when outbound
sync goes live (deferred to v1.1; the engine in `integrations/tasks.py` is
`NotImplementedError` today, so **no push fires at the M1 cutover**), a
missing id makes Zoho INSERT a new record instead of UPDATE, orphaning years
of CRM activity. Capture them now or lose them. See
`django_res_design/08-integrations.md` → "Migrating legacy external IDs".

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

**One-shot re-key migration.** Reservations migration
`0035_remove_guestpreference_guest_remove_booking_guest_and_more` does two
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

**Existing-DB upgrade (no fresh rebuild):** migration
`accounts/0012_drop_person_company` is the company→agency backfill for an
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
`django_res_design/10-decisions.md`) — they are only ever set in the new system,
never emitted by the loader. An unmapped/NULL legacy `RoleId` falls back to
`owner`.

> ⚠️ **Verify before cutover — role source completeness.** The loader sources
> `RoleId` only from the LEFT-JOINed `VillaContactRoleMapping`. The schema doc
> (`07-api-schema-reconciliation.md`) notes `VillaRoles` is *also* FK'd from the
> base `VillaContactMapping`. If any mapping carries its own `RoleId` with **no**
> child role-mapping row, it currently imports as `owner` (the NULL fallback),
> silently dropping the real role. **Count** `VillaContactMapping` rows with a
> non-null `RoleId` but no `VillaContactRoleMapping` child against the dump; if
> non-zero, source the role via `COALESCE(r.RoleId, m.RoleId)` in the loader's
> `legacy_query`. This is a pre-existing loader gap surfaced (not introduced) by
> the GAP-048 remap.

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
| `VillaFinance`            | 1236         | 413 contact-default rows mirror onto `GroupFinance` (no 1:1 mapping); 676 parent-child override rows have no schema equivalent. |
| `VillaCurrency`           | 4            | Junk rows (`HTFG`/`RUPEE`/`RS`) with zero FK references are skipped. |
| `VillaSeasonRate`         | 3727         | 3462 pre-resolver gap (rows with no price — unusable in legacy too — plus rows on the 67 unloaded seasons) + 265 rows newly dropped by overlap resolution (see below; 389 total drops, but 124 sit on unloaded seasons and were already counted). |
| `VillaMaster`             | 1            | One row with empty `Name`. |
| `VillaContactMapping`     | 1            | Composite legacy_id collapse. |
| `VillaClientDetails`      | 1            | One row with neither `FirstName` nor `LastName` (no identity to import). Loads to the `client-` slice of `Person` (GAP-045). |

Any other gap is a **blocker**. Track it down before proceeding.

### Rate rule overlap resolution

Legacy had no rate-precedence concept: its per-night lookup was an unordered
`SELECT TOP 1` (`sp_get_quote_weeks_price`) / `FirstOrDefault` over an
unordered `DISTINCT` (`ResService.cs`), so the winner among overlapping
`VillaSeasonRate` rows was formally arbitrary (de-facto lowest ID via the
clustered index). The new schema forbids within-card overlap outright
(`raterule_no_overlap` EXCLUDE constraint), so `RateRuleLoader` resolves
overlaps at load time via `resolve_rate_rule_overlaps`:

- **Boundary trim** — legacy stored checkout-style contiguous bands (the next
  band starts on the day the previous one ends) but looked them up
  inclusively. The new model is inclusive on both ends, so the earlier row's
  end is trimmed back one day when a party-overlapping sibling starts on it.
- **Approved-first tiers** — `IsApprove = 1` rows claim date space before
  unapproved rows, protecting currently-quotable ranges from being clipped by
  unapproved drafts (67 such pairs in the 24-Apr-2025 dump).
- **Earliest legacy ID wins within a tier** — matching legacy's de-facto
  behaviour.
- **Clip-only** — a losing row is clipped to its largest uncovered remainder
  (a winner punched into its middle discards the smaller side) or dropped
  when fully covered. One legacy row maps to at most one rule; legacy IDs are
  never suffixed or split.
- Rows with identical date spans clip the **party bracket** instead; the
  property's capacity resolves unbounded remainders at transform time.

Consequences:

- The loader **ignores `--since`** (and logs a warning if passed) —
  resolution is a function of a season's whole row set, so every pass is a
  full reload (the table is small).
- Each run is a **full replace**: all legacy-loaded rules are purged, then
  the resolver's output is inserted. Inserting into an empty legacy footprint
  means re-runs can never collide with the previous run's spans under the
  EXCLUDE constraint, so a re-run always converges in one pass (the report
  shows `created=N`, not `updated=N`). UI-created rules
  (`legacy_id IS NULL`) are never touched.
- The 389 dropped rows (and trimmed boundary days) mean quoted prices can
  shift versus legacy for the ~38 seasons that had genuinely conflicting
  prices — previously the winner was the highest `ID % 65535` stamp under
  the old per-priority EXCLUDE constraint, and arbitrary in legacy itself.
- The loader logs one summary event per run:
  `data_migration.rate_rule_overlaps_resolved` with `trimmed` / `dropped` /
  `party_clipped` / `purged` counters (24-Apr-2025 dump, first run:
  2281 / 389 / 0 / 0).

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
