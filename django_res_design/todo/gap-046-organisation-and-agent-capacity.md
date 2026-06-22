# GAP-046 — `Organisation` entity + agent capacity (B2B Companies)

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
