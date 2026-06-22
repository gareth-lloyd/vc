# GAP-046 — `Organisation` entity + agent capacity (B2B Companies)

> **✅ RESOLVED (2026-06-22)** — shipped to local `main` (merge `8184ab2`), 7
> units (expand → API → migrate → switch → contract → FE directory → FE swap):
> - **`accounts.Organisation`** (`AuditedModel`, `org_type`-scoped
>   agency/mgmt/supplier; `OrgType`/`OrgStatus` enums; `dedup_key` unique
>   content-hash backfill key kept off `legacy_id`; lazy-string `country` FK;
>   `merge()` repoints agents + `record_merge`, no `scrub_pii`) + audit tracking
>   + `OrganisationFactory` — `476852e`.
> - **`Person.agency`** FK → Organisation (PROTECT, `related_name="agents"`);
>   contact API exposes writable `agency` + read-only `agency_detail` — `5df07d5`.
> - **Organisation API** (ViewSet + serializer + filterset + `:merge` colon-verb,
>   mirrors ContactViewSet) — `460c331`.
> - **company-string → Organisation** migration path: framework-free
>   `organisation_for_company_name()` helper, loader reroute (writes `agency`, not
>   `company`), `dedupe_organisations --dry-run` fuzzy reporter (stdlib difflib,
>   no auto-merge), `reconcile_legacy` Organisation check, CUTOVER docs —
>   `2859f6f`.
> - **switch all `company` reads → `agency`** (`Person.agency_name` DRY property;
>   `select_related` joins keep query budgets flat) — `c2f965c`.
> - **contract: drop `Person.company`** — migration `0012` = frozen RunPython
>   backfill (module-level `_frozen_company_dedup_key` + sync test) → RemoveField;
>   factory/seed/audit/anonymize cleaned — `e760fbb`.
> - **FE Companies directory** (`/companies`, org_type=agency) + reusable
>   `CompanyPicker`/`CompanyFormDialog` — `c6e0582`.
> - **FE contacts company→agency swap** (CompanyPicker on the contact form, object
>   ↔ PK bridge, inline-create, agency detach; all reads → `agency_detail.name`) —
>   `ef56a8b`.
>
> **Item 3 of the ticket (the `.agent` FK repoint) was already done in GAP-045
> phase-1a** — verified, not re-touched. **Deferred (out of scope, fast-follow):**
> mgmt-company & supplier screens (GAP-048, q-007 — model + enum values land now,
> only the agency screen ships); agent filter in the Clients directory (GAP-047);
> FE `:merge` UI (backend `:merge` + dedupe reporter ship; the fold-one-into-another
> dialog is an admin power-tool beyond the directory MVP). Largely dissolves
> GAP-029 (a company-only contact is now an Organisation). Full FE suite green
> (149 files / 1178 tests); backend gate green.

- **Severity:** Gap (data-model + frontend) — after GAP-045
- **Source:** 2026-06-17 owner Contacts-feature review transcript
  (the B2B "Companies" section + agents); mockup
  `mock_up_analysis/01-new-res-system.md` §2.13.
- **Files:**
  - `django_res/accounts/models/` (new `organisation.py`), `accounts/enums.py`
    (`OrgType`), serializers / views / urls
  - `django_res/accounts/models/person.py` (`agency` / `company` FK)
  - `django_res/reservations/models/{enquiry,quotation,booking}.py`
    (`agent` FKs → `Person`)
  - `data_migration/loaders/` (company-string → Organisation;
    `Enquiry/Quotation/Booking.agent` repoint)
  - `frontend/src/features/companies/` (new directory)

## Problem

The owner wants a **separate Companies section** — add a B2B company (e.g.
"Dune Travel"), attach an agent to it, browse the list. Today `company` is a
**free-text `CharField`** on `Person` (no entity, no list), and the
booking/travel **agent** is an `accounts.Person` FK
(`Enquiry/Quotation/Booking.agent`) — a demand-side role stranded in the
supply-side identity bag. Organisations are simply unmodelled.

## Proposed fix

1. **Add `Organisation`** (in `accounts`): `name`, address, `website_url`,
   `notes`, `status`, `legacy_id`, and an **`org_type`** enum
   (`agency`, `management_company`, `supplier`, …).
2. **Agent capacity** = `Person.agency → Organisation` (FK, null). "Is an
   agent" stays **derived** (has an agency / is referenced as an `.agent`) — no
   `kind` column (per GAP-045).
3. ~~**Repoint the `.agent` FKs** from `Contact` → `Person`.~~ **Already done
   (2026-06-20): GAP-045 phase-1a's in-place Contact→Person rename satisfied this
   trivially** — `Enquiry/Quotation/Booking.agent` already point at
   `accounts.Person` (`enquiry.py:102`, `quotation.py:60`, `booking.py:145`).
   Trim from scope; `Quotation.agent` `PROTECT` already honoured.
4. **Migrate free-text `company` strings → `Organisation` rows**: dedupe
   distinct values (the legacy `SELECT_DISTINCT` company autocomplete is the
   precedent — `workflows/05-directory/contact-records.md:124-134`), attach the
   resulting FK; produce a candidate report, no silent auto-merge.
5. **Companies directory (FE)** + picker; agent-create flow can set/create the
   agency inline.

**Caveat 4 (from the UI assessment):** the **Companies screen** is
`Organisation` filtered to **`org_type=agency`**. The *same* entity under other
`org_type`s backs **management companies** (which surface in Villa Contacts as
property assignees, GAP-048) and **concierge supplier orgs** (q-007) — so the
model is shared, the screens are `org_type`-scoped.

## Acceptance

- `Organisation` exists with `org_type`; agents link via `Person.agency`.
- `.agent` FKs point at `Person`; integrity preserved; `PROTECT` honoured.
- Free-text companies migrated to `Organisation` (with a dedupe report); no
  orphaned company strings remain.
- Companies directory lists `org_type=agency`; management companies reachable
  as assignees in GAP-048.
- `Organisation` registered with `core.audit.track` if it carries PII/contact
  detail.

## Dependencies

Depends on **GAP-045** (Person). Feeds **GAP-048** (Organisation assignees)
and **GAP-047** (agent filter in Clients). Largely **dissolves GAP-029** (a
"company-only contact" is now an `Organisation`). Coordinate `org_type` with
**q-007** (concierge supplier directory).
