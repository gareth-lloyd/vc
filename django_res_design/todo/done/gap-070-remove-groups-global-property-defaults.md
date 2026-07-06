# GAP-070 — Remove property groups + runtime inheritance; global defaults applied at creation

> **✅ RESOLVED (2026-07-06, local `main` unpushed)** — shipped on `feat/gap-070`
> in 9 units. **Problem:** `PropertyGroup` fused organisational grouping onto
> per-group defaults inherited at runtime via `effective()` — unrealised value
> (no operator UI, legacy only ever had a single global `VillaConfigPropertyDefault`)
> at real architectural cost; owner twice asked to drop Villa Groups.
> **Fix:** a global `PropertyDefaults` singleton (pk=1, `get_solo()`, mirrors
> `core.SystemSettings`; `GET/PATCH /property-defaults`, IsReservationsWriter)
> **snapshotted** field-by-field into concrete `PropertySettings`/`PropertyFinance`
> at property creation + duplicate (`properties/services/defaults.py::snapshot_defaults`);
> a freeze migration (`0027`) resolved every existing property's old `effective()`
> outcome into concrete rows, then `PropertyGroup`/`GroupSettings`/`GroupFinance` +
> `Property.group` + both `effective()` impls were deleted. NULL now means
> *genuinely unset*: settings consumers use hardcoded floors (holds 48h, changeover
> ANY, prices GROSS, min-nights 1, pre-approval False), finance NULLs resolve via
> `_POLICY_FALLBACKS` (frozen pre-GAP-070 GroupFinance defaults, deliberately ≠
> PropertyDefaults values). Cutover parity: new `property_defaults` loader (since-skips
> with a warning) + owner-contact finance fallback (`PropertyFinanceLoader`) preserve
> today's contact-default outcome. FE: groups removed from CreatePropertyDialog/schemas,
> new admin `/admin/property-defaults` editor. Notable discovery: legacy changeover
> columns store `ChangeOverDays.Code` (-1/0=Sun/1-6), not an Id — `_DAY_MAP` re-keyed.
> **Commits:** `8cb4f33` (singleton+API) · `74a5556` (creation snapshot) · `f05aed4`
> (freeze `0027`) · `65568d5` (consumer simplification) · `6adffa1`/`1a40e21` (drop
> groups) · `5338d1e` (cutover parity) · `fe97bdd` (FE remove groups) · `31ad760`
> (FE defaults editor) + docs close-out. **Subsumes GAP-068** (its default *values*
> seed the singleton; its features-starter half → GAP-067); **moots FG-002** (deletes
> `effective()`); **reverses FG-003**. Deferred: lightweight organisational tag to
> replace the group facet (separate ticket, if a need resurfaces); NOT NULL column
> tightening; SettingsTab "unset" UX polish (product call for Nick).

- **Severity:** Gap / architecture change (model + migration + FE + docs). Reverses
  the "groups stay" stance of [GAP-068](gap-068-seed-group-finance-settings-defaults.md)
  and [Q-021](done/q-021-defaults-and-feature-taxonomy.md); **subsumes GAP-068**.
- **Source:** owner (Nick) has twice asked to drop Villa Groups (2026-06-11 email;
  reiterated in `owner-questions-2026-07-02.md`). Assessment 2026-07-03 (this
  investigation) found the per-group inheritance is unrealised value at real
  architectural cost — see "Why" below.
- **Files:**
  - Backend models: `properties/models/property.py` (`PropertyGroup`, `Property.group`),
    `properties/models/settings.py` (`PropertySettings`, `GroupSettings`, `effective`),
    `properties/models/finance.py` (`PropertyFinance`, `GroupFinance`, `_FinanceFieldMixin`,
    all `effective_*` builders), `properties/signals.py` (group-row auto-create).
  - New: `properties/models/defaults.py` (`PropertyDefaults` singleton), its serializer,
    a `RetrieveUpdateAPIView`, a route, and the creation-time snapshot in the property
    create service.
  - `effective()` consumers: `reservations/services/holds.py:48`,
    `reservations/services/availability.py:111-112`, `pricing/services/engine.py:584,592`,
    `pricing/services/currency.py:44,47`, `properties/services/changeover.py:58,60`,
    `properties/services/timing.py:31`, `properties/filters/property.py:103`,
    `reservations/serializers/booking.py:230,234`, `reservations/services/charges.py`,
    `payments/services/{payment_scheduler,security_deposit,refund}.py`,
    `properties/serializers/settings.py` (the `*_effective` / `currency_code` projections),
    and the `group__settings` / `group__finance` `select_related` in
    `reservations/views/{booking,owner}.py` + `reservations/services/stay_options.py`.
  - Data migration: `data_migration/loaders/properties.py` (`PropertyGroupLoader`,
    `_sentinel_group`), `data_migration/loaders/finance.py` (`GroupFinanceLoader` +
    owner-contact-per-group mirror `:213,266`), `data_migration/loaders/sentinels.py`
    (`unknown_group`), `reconcile_legacy`, `reservations/management/commands/demo_ical.py:624`.
  - Frontend: `features/properties/tabs/SettingsTab.tsx` (drop `INHERIT_VALUE`),
    `features/properties/components/CreatePropertyDialog.tsx` (drop group picker),
    `features/properties/{api,hooks,schemas}.ts` (drop `propertyGroups*`), plus a **new**
    global-defaults editor screen + hooks/schema.
  - Docs: `02-properties.md`, `03-finance-config.md`, `10-decisions.md`,
    `django_res/CLAUDE.md` (the "Inheritance — call `effective(field)`" convention).

## Why (the case for the change)

Two things are fused onto a mandatory `PropertyGroup`: (a) **organisational grouping**
(`Property.group` non-null `PROTECT` FK, list-filter facet) and (b) **per-group defaults**
(`GroupSettings`/`GroupFinance` "floor" rows that `PropertySettings`/`PropertyFinance`
inherit via `effective()`).

- The **defaults half has no operator UI** — group defaults are editable only in Django
  admin (unreachable by ops). In practice every group sits at the hard-coded model
  defaults and properties override individually, so the group indirection currently adds
  nothing over plain system defaults.
- **Legacy never scoped defaults to groups.** ResSystem had a *single global*
  `VillaConfigPropertyDefault` row (one admin tab) plus a *separate* organisational
  `VillaGroup`. The rebuild generalised global→per-group — a generalisation nobody asked
  for. `owner-questions-2026-07-02.md` §B1 confirms the business wants **one** starter set
  ("the defaults every new villa starts with… all changeable per villa, this just saves
  re-typing"), and GAP-068's own plan seeds only "the production cutover group(s)".
- **Runtime inheritance is unnecessary.** Defaults matter exactly once — at villa
  creation. There is no requirement to retroactively re-flow a changed default into
  existing villas; the owner explicitly frames them as a create-time convenience.

## Target design

1. **`PropertyDefaults` singleton** (`properties/models/defaults.py`) — typed columns
   mirroring every field currently on `GroupSettings` **and** `GroupFinance` (the
   create-time starter set). One row, `pk=1`, `get_solo()` — mirror the proven
   `core.models.system_settings.SystemSettings` pattern (and the legacy typed
   `VillaConfigPropertyDefault`, which this faithfully restores). Currency/RatePlan FKs
   stay string-referenced, as today, so the properties→pricing spine edge is unchanged.
   - Operator-editable at `GET/PATCH /property-defaults` (singleton sub-resource — no
     `POST`/`DELETE`), role-gated (`IsReservationsWriter`, as the group views were).
   - **This is the editing UI the feature always lacked.**

2. **Creation-time snapshot.** The property-create service copies `PropertyDefaults`
   into the new property's `PropertySettings`/`PropertyFinance` rows as concrete values.
   After creation they are plain, independently-editable attributes; changing the global
   defaults never touches existing villas. `CreatePropertyDialog` may prefill the form
   from `/property-defaults` so the operator can tweak per-villa at creation.

3. **`PropertySettings`/`PropertyFinance` become concrete.** `null` no longer means
   "inherit" — it means "genuinely unset" (only for legitimately-optional fields; e.g.
   `currency`). Give the required fields real DB/column defaults so a property always
   resolves a value without a resolver. **Recommended low-risk path:** keep the columns
   nullable (no giant `NOT NULL` migration) but change the *semantics* and delete
   `effective()`; consumers read the attribute directly, with a hardcoded final fallback
   only where a field can still be null (e.g. `hold_duration_hours` → 48).

4. **Delete `PropertyGroup`, `GroupSettings`, `GroupFinance`, `Property.group`,** the
   `create_group_*` signals, the group viewset/routes/serializer/admin, and both
   `effective()` implementations. `properties/filters/property.py` `group` facet and the
   `group__settings__changeover_day` fallback in the `ANY`-changeover filter collapse to
   `settings__changeover_day`.

## Migration plan (order matters — freeze before drop)

1. **Add** `PropertyDefaults`; seed it from the current `GroupSettings`/`GroupFinance`
   values (or, at cutover, the GAP-068 confirmed set: deposit required/PERCENT/30 · SD
   required/FIXED · commission PERCENT · check-in 16:30 / check-out 10:30). Legacy path:
   seed from the single `VillaConfigPropertyDefault` row.
2. **Freeze** — data migration that, for every existing property, runs the *old*
   `effective()` resolution one final time and writes the resolved concrete value into
   `PropertySettings`/`PropertyFinance`. Currently-inheriting nulls become explicit
   values. (Must run while the group tables still exist.)
3. **Drop** `Property.group` FK, then `GroupSettings`/`GroupFinance`/`PropertyGroup`, in
   dependency order. Remove the auto-create signals in the same migration window.
4. Simplify every `effective()` consumer to a direct attribute read; drop the
   `group__*` `select_related` joins; keep query-count pins green.

## Data-migration (legacy loader) impact

- Drop `PropertyGroupLoader`, `_sentinel_group`/`unknown_group()`, and group resolution
  in `PropertyLoader` — properties load group-less.
- Drop `GroupFinanceLoader` and the per-group OWNER-contact default mirror
  (`finance.py:213,266`); confirm no group-scoped owner-contact behaviour is lost.
- Seed `PropertyDefaults` from legacy `VillaConfigPropertyDefault` (faithful: legacy
  defaults *were* global). Update `reconcile_legacy` to drop group counts.

## Frontend impact

- `SettingsTab.tsx` — remove `INHERIT_VALUE` sentinel + every "inherit" `<Select>`
  option; each field becomes a plain concrete input. Remove the "client can't see the
  inherited value" workaround (comment `SettingsTab.tsx:406`).
- `CreatePropertyDialog.tsx` — remove the required group picker; optionally prefill from
  `/property-defaults`.
- Delete `fetchPropertyGroups`/`usePropertyGroups`/`propertyGroupSchema` and the property
  `group` FK field; the `*_effective` / group-resolved `currency_code` projections in
  `propertySettingsSchema` collapse to the property's own fields (keep `currency_code` as
  a plain denorm if the FE money adornment from GAP-026 still needs the ISO code).
- **New:** a global "Property defaults" editor screen (admin/settings area) over
  `GET/PATCH /property-defaults`, with hooks + schema.

## Open decisions to confirm before build

1. **Grouping-as-organisation.** The owner asked to remove groups outright, but `group`
   is a live **list-filter facet** today (`filters/property.py:26`) and legacy also used
   groups for filtering + group-shared contacts. Confirm no organisational/filter/
   reporting need survives removal — if one does, it should return as a lightweight tag,
   **out of scope for this ticket**, not as the defaults-bearing entity.
2. **Currency floor.** `GroupSettings.currency` was nullable (could resolve to `None`).
   Set a global default currency so new villas always get one; decide backfill vs
   leave-null for existing null-currency properties at freeze time.
3. **Column tightening.** Keep settings/finance columns nullable-with-new-semantics
   (recommended, low-risk) vs a full `NOT NULL` migration. Pick one.

## Acceptance

- `PropertyDefaults` singleton exists, seeded, editable via `GET/PATCH /property-defaults`
  and a role-gated FE screen; creating a property snapshots the defaults into concrete
  `PropertySettings`/`PropertyFinance` values.
- Changing a global default does **not** alter any existing property (test).
- `PropertyGroup`/`GroupSettings`/`GroupFinance`/`Property.group`/`effective()` are gone;
  all former consumers read attributes directly; query-count pins green; full pytest +
  vitest green; `reconcile_legacy` clean of group counts.
- Freeze migration proven to preserve each property's previously-effective values (test
  comparing pre-freeze `effective()` output to post-freeze stored value).
- Decisions recorded in `10-decisions.md`; `02-properties.md` / `03-finance-config.md`
  rewritten; the `effective()` convention removed from `django_res/CLAUDE.md`.

## Dependencies / relationships

- **Subsumes [GAP-068](gap-068-seed-group-finance-settings-defaults.md)** — its
  "seed group defaults" goal is replaced by "seed the global `PropertyDefaults` singleton
  + build its UI". Retire GAP-068 when this lands (its included-features starter-set half
  belongs with **GAP-067**, unaffected).
- **Moots [FG-002](fg-002-effective-null-vs-empty-string.md)** — `effective()`'s
  `""`-vs-`NULL` conflation disappears with the resolver. Close on landing.
- **Reverses [FG-003](done/fg-003-effective-crashes-on-null-group.md)** — its fix
  (non-null `Property.group`) is undone by dropping the FK.
- **Check [GAP-026](done/gap-026-currency-display-money-fields.md)** — the FE money
  adornment consumes the group-resolved `currency_code`; ensure it still works once that
  becomes the property's own currency.
</content>
</invoke>
