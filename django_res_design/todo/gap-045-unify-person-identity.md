> **🟨 PARTIAL (2026-06-20, per `CRITIQUE-2026-06-19.md`)** — Phase 1a has landed
> (~`a4264a9`, 2026-06-18): `accounts.Contact` renamed to `Person` in place
> (`accounts/models/person.py:19`, migration `0006`); supply-side + agent FKs
> repointed to `accounts.Person` (`enquiry.py:102`, `quotation.py:60`,
> `booking.py:145`, `properties/models/contacts.py`, `finance.py`). **The hard
> 2/3 is undone:** `reservations.Guest` still exists as a separate `AuditedModel`
> with its own merge/anonymize and `town/post_code/country` fields, and
> `Enquiry/Quotation/Booking.guest` still point at it. Remaining = phases 2–3
> below (add Guest's fields/constraints + `PersonEmail/PersonPhone` to `Person`,
> data-migrate + repoint guest FKs, unify status/merge, retire `Guest`).
> Downstream GAP-046/047/048/042/040/041 stays blocked until that lands.
>
> _Original ticket preserved below for context._

# GAP-045 — Unify human identity into a single `Person` model

- **Severity:** Gap (foundational data-model refactor) — **do first; blocks
  GAP-047 / GAP-046 / GAP-048**
- **Source:** 2026-06-17 owner Contacts-feature review transcript; domain
  re-assessment recorded in `people-model-cleanup.md` (2026-06-18 banner) and
  `10-decisions.md`.
- **Files:**
  - `django_res/accounts/models/contact.py` (→ `person.py`), `accounts/enums.py`,
    `accounts/serializers/`, `accounts/views/`, `accounts/apps.py`
    (`core.audit.track` registration)
  - `django_res/reservations/models/guest.py` (folded in + retired),
    `reservations/models/{enquiry,quotation,booking}.py` (`guest` FKs),
    `reservations/models/booking.py` (`BookingGuest.guest`),
    `reservations/views/guest.py` (re-homed on Person)
  - `django_res/properties/models/contacts.py`
    (`PropertyContactAssignment.contact`), `properties/models/finance.py`
    (`PropertyFinance.contact`)
  - `data_migration/loaders/` (Contact + Guest loaders), `core/audit.py`
  - `frontend/src/features/contacts/`, `frontend/src/features/guests/`

## Problem

The system fragments **one human identity across two tables**:
`reservations.Guest` (the traveller / renter) and `accounts.Contact` (owners,
managers, housekeepers — **and**, wrongly, the demand-side travel agent via
`Enquiry/Quotation/Booking.agent`). The same human who is both a villa owner
and a guest is two unlinked rows; "agent" — a customer-side role that
*represents the guest* — sits in the supply-side `Contact` bag alongside
owners. This is the root cause behind the owner's "an agent is effectively a
client" feedback and the absent Clients directory.

The domain pass (see `people-model-cleanup.md` banner) established three
invariants the schema must honour: **identity ≠ role ≠ login**; **person ≠
organisation**; **login is a facet**.

## Proposed fix

Evolve **`accounts.Contact` in place into `Person`** (do *not* green-field a
third model) and **fold `reservations.Guest` into it**. `Person` lives in
`accounts` (spine bottom; layer-safe — `accounts` imports no domain app), so
`reservations`/`properties` FKs pointing up are fine.

`Person` carries the union, de-duplicated:
- title / first_name / last_name; child **`PersonEmail` / `PersonPhone`**
  tables (Contact's multi-channel pattern — this **resolves** the deferred
  "Guest channel richness" item).
- **Rich address**: `address_line_1/2 + town + post_code + country` — use
  `country_code` + `get_country()` per the global Django convention, **not**
  free-text country. (Subsumes the address ask in GAP-048.)
- `preferred_method`, `marketing_consent`, `notes`, `status` (unify
  Contact's `INACTIVE` and Guest's `ARCHIVED` into one enum), `legacy_id`,
  `user` (`OneToOne → User`, unchanged — **`User` stays first-class**).
- Guest's **contactability** + **actionable-preference** CHECK constraints
  (ACTIVE-only scope) and **E.164 normalization / advisory dedup** — moved onto
  `Person` verbatim from `people-model-cleanup.md`.
- Unified `merge()` / `anonymize()` — the existing `_meta.related_objects`
  FK-walk already generalises (it walks whatever relations exist); merge
  `Contact.merge` + `Guest.merge` into one, and the two `_AUDIT_PII_FIELDS`
  sets into one.

Repoint every people FK to `Person`: `Enquiry/Quotation/Booking.guest`,
`BookingGuest.guest`, `PropertyContactAssignment.contact`,
`PropertyFinance.contact`. `BookingGuest` **survives** (occupancy roles
LEAD/CO_TRAVELLER are a per-booking relationship, not identity). The `.agent`
FKs are repointed in **GAP-046** (they ride with the Organisation/agent work).

**Phased** (matches the repo's small-commit / TDD norm; not big-bang):
1. Add Guest's fields + constraints to `Contact`; add `PersonEmail/PersonPhone`
   (or migrate `ContactEmail/Phone`); rename `Contact → Person` with a model
   alias kept temporarily.
2. Data-migrate `Guest` rows into `Person` (dedup-on-import report — reuse the
   `people-model-cleanup.md` no-auto-merge-by-email evidence); repoint guest
   FKs; keep `/guests` responding (compat view) during SPA migration.
3. Retire the `Guest` model + compat shims once the SPA is cut over.

**Caveat 3 (from the UI assessment):** the owner's directories (Clients / Villa
Contacts / Companies) are **filtered views** over `Person`, and capacity is
derived (`EXISTS` over PropertyContactAssignment / agency / BookingGuest), not a
column. **Index the capacity predicates** and pin the directory lists with
`core.tests.assert_max_queries`. If the owner's filter chips feel slow, the
escape hatch is a **signal-maintained denormalised capacity flag** (a cache,
never the source of truth) — record it, don't build it pre-emptively.

## Acceptance

- One `accounts.Person` model; `reservations.Guest` retired; all guest FKs
  repointed with integrity preserved (`Quotation.guest` is `PROTECT`).
- `User` unchanged and `OneToOne → Person`; `Enquiry.assigned_to → User`
  (internal salesperson) untouched and still distinct from the agent.
- Unified `merge()`/`anonymize()` with audit PII scrub; `core.audit.track`
  re-registered for `Person` (+ `EXPECTED_TRACKED_MODELS` updated same commit);
  contactability + actionable-preference CHECKs migrated and tested.
- Dedup-on-import report produced; no `@noemail.local` synthetics survive.
- At least one directory list pinned with `assert_max_queries`.

## Dependencies

Foundational. Blocks **GAP-046** (Organisation + agent FK repoint),
**GAP-047** (Clients directory), **GAP-048** (Villa Contacts directory).
Overturns `people-model-cleanup.md` locked decision #1 (banner + `10-decisions`
entry land with this ticket). Relates to FG-005 (system-actor) only via the
shared audit registry.
