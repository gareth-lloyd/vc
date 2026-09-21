# GAP-096 — First-class Zoho push kinds for reference data: `Organisation` (no push of its own) and `Region`/`Country` (edits never re-push)

> **✅ The `organisation` half is BUILT and dark-landed (2026-09-20)** —
> commits `fa4a1d62` (payload builder), `783fd739` (kind registration,
> settings, backfill ordering) and `26ce9eeb` (`zoho_send_sample` steps). The
> ticket **stays in `todo/`**: the `region` half below is unbuilt, and the
> switch-on (setting `ZOHO_FLOW_WEBHOOK_ORGANISATION` and running
> `zoho_backfill --kinds organisation`) has deliberately **not** happened —
> see §"What is left" for exactly what remains.
>
> **One step inverted.** The planned step (1), "fatten
> `_organisation_summary` from 6 keys to the full `_agency_payload` shape",
> was **dropped, not deferred**. Under the "one writer per CRM module"
> principle adopted 2026-09-20 —
> [GAP-119](gap-119-one-writer-per-crm-module.md) — that embedded copy should
> get *thinner*, not fatter: once the villa Flow looks the Account up by
> `RES_ID` it needs nothing but the link. Fattening it would have added
> fields to the live `villa` wire payload purely to feed the inline create
> this ticket exists to eliminate. With that step gone, **no live wire
> contract changed at all** — the `contact` and `villa` payloads are
> byte-identical to before, and everything new sits behind an empty
> `ZOHO_FLOW_WEBHOOKS["organisation"]`.
>
> **Scope widened 2026-09-16 (todo consolidation):** absorbs **GAP-103**
> (Region/Country edits never reach Zoho — no geo push kind, no parent bump)
> — see §"Merged from GAP-103" at the end. The `region` kind is the same
> build as the `organisation` kind below (dedicated kind, dark-landed
> builder, a stage near the front of `zoho_backfill`, never a fan-out), and
> both webhook URLs were requested from Limitless in one email. Suggested
> landing: `organisation` first (it has the settled design), then `region`
> on the same pattern. Before building `region`, get the hub-page answer in
> **Q-026** (was Q-027): if hubs are ever Res-fed this kind becomes their
> delivery route.

- **Severity:** 🟠 Gap (CRM Accounts are created as a side effect and go
  stale; blocks the agency half of the contact mapping).
- **Source:** 2026-09-01 review of Limitless' `limitless_upsert_villa` and
  `limitless_parse_res_contact` against our payloads.
- **Status:** design **settled 2026-09-16** on the dedicated `organisation`
  kind below; the endpoint was **requested from Limitless by email on
  2026-09-16**, asked alongside GAP-103's `region` endpoint (one
  conversation, two URLs — coordination cost is per-conversation, not per
  endpoint). **The `organisation` URL arrived 2026-09-18** (dev/sandbox; Greg
  Robson, in the "RES to Zoho — Sandbox Connections" thread), so **nothing
  external gates this ticket any more** — it is a straight build with a URL
  already waiting for it, and the no-new-endpoint fallback under "Considered
  alternatives" is now dead rather than held in reserve. The `region` half of
  the ask was **not** issued: see §"Merged from GAP-103". The res half was
  never gated on their reply anyway: see "Landing order".
- **Files touched (built 2026-09-20; line numbers refreshed):**
  - `django_res/integrations/apps.py:151` — where `Person` registers as the
    `contact` kind; `Organisation` registers immediately after it.
  - `django_res/integrations/services/zoho_payloads.py` —
    `_agency_payload` is already the shape an organisation payload wants;
    lift it to a `build_organisation_payload`.
  - `django_res/properties/services/zoho_payload.py` —
    `_organisation_summary` (the villa-embedded copy).
  - `django_res/integrations/services/zoho_flow.py:41` — `ZOHO_FLOW_KINDS`.
  - `django_res/villacollective/settings/base.py:248` +
    `settings/test.py:78` — the `ZOHO_FLOW_WEBHOOKS` key (empty default) and
    `.env.example`; `integrations/tests/test_zoho_flow.py:194` asserts the
    kinds and the setting's keys match, so both move together.
  - `django_res/integrations/management/commands/zoho_backfill.py:51` —
    `KIND_ORDER`.

## Problem

Registered push kinds today are `contact` (Person), `enquiry`, `quotation`,
`booking` and `villa` (Property). `accounts.Organisation` is not among them,
and three consequences follow — all of which surfaced as apparent Flow bugs
before tracing back here:

1. **CRM Accounts exist only as a villa side effect.** `limitless_upsert_villa`
   creates/updates an Account from `contacts[role=management_company]
   .organisation`. That is the *only* path by which an Organisation becomes
   an Account.
2. **Agency organisations never become Accounts at all.** The contact flow
   writes `Contact_Type: "Agency"` as text on the Contact and stops there, so
   the B2B directory GAP-046 built has no CRM counterpart. Our contact
   payload already sends a keyed `agency` sub-object (`RES_ID`, `id`, `name`,
   address, `org_type`, `status`) that has nowhere to land.
3. **Renames never propagate.** `Organisation` is not in `_VILLA_CHILDREN`
   (`properties/signals.py:99`) — correctly, since it is not a child of one
   property — so editing an organisation bumps nothing. `Account_Name` can
   stay wrong indefinitely, and the villa payload docstring already records
   this class of staleness as an accepted trade-off for *embedded catalog
   copies*. It is not an acceptable trade-off for the Account record itself.

Adding a bump receiver would be the wrong fix: an organisation can be the
management company of many villas, so an edit would fan out N villa pushes to
refresh one Account name.

## Proposed fix

Register `Organisation` as its own kind, mirroring the `contact` pattern:

- `register_zoho_flow(Organisation, kind="organisation",
  build_payload=build_organisation_payload)` with `auto_push=True`.
- Payload from the existing `_agency_payload` shape (`RES_ID`, `id`, `name`,
  `org_type`, `email`, `phone`, address block, `country`, `website_url`,
  `notes`, `status`), plus `created_at`/`updated_at`.
- New `ZOHO_FLOW_WEBHOOKS["organisation"]` key, **defaulting to `""`**.
  Requested from Limitless 2026-09-16, **delivered 2026-09-18** — dev/sandbox
  only; the production list is a separate issue, last sent 2026-09-03 and now
  stale (see "Endpoint churn"). The URL is the credential (zapikey-in-URL),
  so it lives in the env and never in this repo.
- ~~**Fatten the villa-embedded copy.**~~ **Dropped 2026-09-20** — see the
  banner at the top. `_organisation_summary`
  (`properties/services/zoho_payload.py:146`) still sends its 6 keys
  (RES_ID, id, name, org_type, email, phone), and under
  [GAP-119](gap-119-one-writer-per-crm-module.md) its next move is *down* to
  three, once the villa Flow switches to a lookup (CHECK-003 §Dependencies,
  **not** its item 2 — that one only fixes *which* management company is
  picked). It now carries an inline comment saying so, as does
  `_agency_payload`, so neither is thinned ahead of its switch. The original rationale — "completes the
  Account during the transition" — assumed the villa flow would keep creating
  Accounts; the point of this ticket is that it stops.
- Extend `zoho_backfill` ordering: organisation **before** contact and villa,
  so the Account exists before anything looks it up.
- **Villa before booking**, for the same reason (added 2026-09-02, off the
  booking-flow review). `limitless_insert_booking` COQLs `Products` by
  `RES_ID` and, on a miss, creates a *stub* villa from the thin `region`
  object the booking payload carries — no location, no capacity, no rooms,
  no features, and a free-text `Region`/`Country`. That stub is a
  second-class Product the villa upsert then has to reconcile, and its
  duplicate-name branch is where CHECK-004 item 6 (booking attached to the
  wrong villa) becomes reachable. The stub path is a legitimate safety net,
  but it should be rare: emitting villas ahead of bookings makes it so. Full
  ordering: organisation → contact → villa → enquiry → booking.
- Once it exists, the villa flow's inline Account create/update becomes a
  lookup, and the contact flow can set a real Account lookup instead of the
  `Contact_Type` text. Both are Limitless-side follow-ups, **recorded
  2026-09-18 on CHECK-001 and CHECK-003** now that the endpoint exists to
  make them reachable. Neither can be verified until we have pushed
  organisations, so sequence them after step (3) below.

No erasure concern: `OrgStatus` has no ANONYMIZED member by design (an
organisation is not a data subject — see `accounts/enums.py`), so the
GAP-095 question does not extend here.

## Landing order — the res half is not blocked

`webhook_url()` returns `""` for an unset kind and `enqueue_zoho_push`
no-ops on a falsy URL (`integrations/services/zoho_flow.py:185,275`), so
this ticket lands **dark**: registration, payload builder, backfill stage
and every test below can merge behind an empty default, and nothing reaches
Zoho until the env var is set. "Waiting on Limitless" gates the *switch-on*,
not the build. Tests drive the path with `override_settings`, as the other
kinds' tests do.

Sequence: ~~(1) fatten `_organisation_summary`~~ **dropped, see the banner**;
**(2) register the kind + builder + backfill stage, dark — DONE 2026-09-20**;
(3) set the URL — **it arrived 2026-09-18**, so this is now a config step, not
a wait — and run `zoho_backfill --kinds organisation`; (4) their two Flow
follow-ups (CHECK-001, CHECK-003), which only become verifiable after (3).

## What is left

1. **Set `ZOHO_FLOW_WEBHOOK_ORGANISATION`** (dev first). Re-check every other
   dev URL in the same pass — Limitless rotated the dev `villas` and
   `enquiries` zapikeys on 2026-09-18 (§"Endpoint churn") and the production
   list is the 2026-09-03 one, which has five kinds and no `organisation`.
2. **Run `zoho_backfill --kinds organisation`**, then the flows' own kinds if
   anything else is stale.
3. **CHECK-001 (items 2, 6) / CHECK-003 §Dependencies / CHECK-002 item 3** —
   Limitless-side, now
   unblocked by (2). Push-and-read verification each, per GAP-097.
4. **The `region` half** — no URL issued, Q-026 still open.

Three residuals were accepted knowingly when the kind was registered, all
recorded in `integrations/apps.py`:

- `Organisation.merge` repoints `Person.agency` by bulk `.update()` (no
  signals), so member contacts stay stale until their next own bump.
- Registering the kind connects the `post_delete` `SyncRecord` reaper, so a
  merge drops the absorbed org's local record while its CRM Account survives
  unreferenced (there is no delete endpoint). Org merges are routine — the
  `dedup_key` machinery exists because orgs are minted from free-text company
  strings — so this wants a Limitless-side sweep **before** the URL is set,
  not after.
- Villas are not bumped on an organisation save (nothing fans out
  Organisation → Property), so a rename leaves the old name on managed villas
  until an unrelated villa save. The fix is CHECK-003 §Dependencies' lookup by
  `RES_ID`, not a
  fan-out that would cost one villa push per managed property. Pinned by
  `test_organisation_rename_pushes_once_not_once_per_managed_villa`.

### Endpoint churn (2026-09-18)

Switching this kind on is **not** a one-key change. In the same round of
emails Limitless reorganised the Flows into a "RES Villa Webhook" folder
built on shared sub-flows (one contact-upsert routine, called by the villa
and enquiry flows rather than duplicated into each), and re-issued the dev
URLs: `contacts` unchanged, **`villas` and `enquiries` both rotated**. So
re-check every dev value in the env at the same time as adding
`organisation`, or the two rotated kinds will post to a dead zapikey and
`enqueue_zoho_push` will record the failure as a delivery problem rather than
a stale credential. The **production** list is older still — 2026-09-03, five
kinds, no `organisation` — and predates the reorganisation entirely, so ask
for a fresh production set before any live switch-on.

## Considered alternatives

**Rejected 2026-09-16: no new kind — enrich the embedded copies and replace
`_organisation_changed`'s fan-out with a single "carrier" push** (one
non-anonymized agent by pk, else one `property_assignments` villa by pk).
It meets the one-push criterion and needs no new endpoint, but it loses four
things the dedicated kind gives:

- **No `SyncRecord` per organisation** — no PENDING/IN_SYNC/ERROR state, no
  `push_pending` sweep coverage (the sweep iterates `registered_zoho_models`),
  so a failed push leaves an org silently stale. Also degrades GAP-097 and
  GAP-028 before they are built.
- **No `zoho_backfill --kinds organisation`** — orgs could only be replayed
  by proxy, via contacts and villas, with incomplete coverage.
- **Coverage by accident, not by existence** — an org with no agents and no
  villa assignment never reaches the CRM; one whose only agent is ANONYMIZED
  is unpushable (`is_anonymized_person` no-ops the enqueue).
- **Two writers to Accounts, permanently** — the villa flow's inline create
  would stay alongside the contact flow's. CHECK-004 item 7 is that exact
  pattern going wrong on Contacts.

Also: the villa-carrier branch would add org edits as another villa-push
trigger, and CHECK-003 item 3 has villa re-pushes possibly re-creating rooms
subform rows. ~~Keep as the fallback **only** if Limitless decline the
endpoint; the payload enrichment above is its foundation either way.~~
**Dead 2026-09-20:** the endpoint was delivered and the kind is built, so
there is nothing left to fall back to — and the enrichment that was to be its
foundation was dropped, not deferred (see the banner). Kept here as the record
of an argument, not as a plan.

**Rejected: alias `organisation` onto the existing contact webhook**,
branching on the GAP-102 `_meta.kind` discriminator. Res-side identical, no
new endpoint — but a Zoho Flow webhook trigger pins its payload schema from
a sample, so Limitless would have to re-sample the contact Flow against a
union of two shapes and branch before any mapping. Comparable effort to a
new Flow, more fragile (a missed branch feeds an organisation into the
Contact mapping), and it collapses two object types into one execution log
and one zapikey.

## Acceptance

- ✅ Saving an `Organisation` enqueues an `organisation` push.
  (`test_organisation_save_enqueues_exactly_one_organisation_push`)
- ✅ The payload carries every CRM-relevant column, JSON-safe.
  (`test_organisation_payload_carries_the_full_field_set` + the round-trip and
  ISO-timestamp tests. `legacy_id` is deliberately omitted — NULL on every
  org today, `dedup_key` being the internal backfill key — and the builder's
  docstring says so.)
- ✅ `zoho_backfill` emits organisation → contact → villa → enquiry → quote
  → booking, in that order (`KIND_ORDER`,
  `integrations/management/commands/zoho_backfill.py:51`; the earlier
  five-kind phrasing above omitted `quote`).
  (`test_pushes_kinds_in_dependency_order_and_records_sync_run`)
- ✅ Renaming an organisation results in exactly ONE push, not one per villa
  it manages.
  (`test_organisation_rename_pushes_once_not_once_per_managed_villa` — records
  are settled to `IN_SYNC` first, or the enqueue dedupe would hide a fan-out
  rather than prove its absence)
- ~~The villa-embedded `organisation` object carries the same fields as the
  contact payload's `agency` object.~~ **Inverted 2026-09-20** — the two
  copies are now expected to *diverge*, and to converge downward on
  `RES_ID`/`id`/`name`, each behind its own Flow's switch to a lookup
  ([GAP-119](gap-119-one-writer-per-crm-module.md)). The anti-drift concern
  the criterion was protecting against is handled by the inline comments on
  both functions.
- ✅ With `ZOHO_FLOW_WEBHOOKS["organisation"] == ""`, saving an Organisation
  writes no `SyncRecord` and dispatches nothing.
  (`test_organisation_push_is_dark_without_a_webhook_url`; the drift guard
  `test_test_settings_hard_disable_all_webhooks` keeps the kinds tuple and the
  settings dict in step)
- ⬜ A villa's management-company Account is found by lookup, not created by
  the villa flow. (verified Zoho-side, CHECK-003 — needs the switch-on first)

## Dependencies

- **Webhook URL requested 2026-09-16, delivered 2026-09-18** (dev; same
  coordination shape as the villa/booking kinds in GAP-082). It was asked
  bundled with GAP-103's `region` endpoint but only the `organisation` half
  came back, so the `region` URL is still outstanding and is now the only
  external dependency left on this ticket.
- **CHECK-003** item 2 — picking the *right* management company is
  orthogonal and can land first; this ticket changes where the Account comes
  from, not which one is chosen.
- **CHECK-001** — the agency half of the contact mapping is blocked on this.
  Note no res-side change can unblock it alone: `limitless_upsert_villa` is
  the only path into the Accounts module, and an agency has no villa, so the
  Account cannot exist until Limitless write to it from somewhere else.
  Unblocked on their side as of 2026-09-18; blocked on ours until we push.
- **CHECK-002** item 3 (`Agency` points at the person, `agent` dropped) is
  the third consumer, and Limitless have now made the coupling explicit: the
  2026-09-18 enquiry-flow response records *"resolve Agency and upsert and
  pass through — will await organisation endpoint data first"*. The endpoint
  they are waiting on is the one they themselves issued the same day, so that
  item now waits on **our** first `organisation` push, not on them.
- Merged **GAP-103** (`region` kind) — asked in the same email, same
  pattern; if they quote both, land them together. Its own dependencies
  (GAP-102, CHECK-002's Countries-of-Interest picklist) are in §"Merged from
  GAP-103".
- **Q-026** (hub-page question, was Q-027) — answer before the `region`
  kind is built.
- **GAP-046** — the Organisation model this pushes.
- **[GAP-119](gap-119-one-writer-per-crm-module.md)** — the principle this
  ticket's build was the first instance of, and where every embed's thinning
  is now tracked. Filed 2026-09-20 out of this work.

---

## Merged from GAP-103 — Region/Country edits never reach Zoho (no geo push kind, no parent bump)

> _Folded in 2026-09-16 (todo consolidation). The standalone ticket is closed as
> [GAP-103](done/gap-103-region-country-edits-never-repush.md); the text below is that ticket as it stood, headings
> demoted one level. A reference to GAP-103 elsewhere now means this section._

> **2026-09-18 — the CRM half now exists; the delivery route does not.**
> Answering CHECK-002's Countries-of-Interest decision, Limitless built a
> **Regions custom module** in the sandbox CRM (region name, RES ID, country
> picklist) with a linking module behind it giving many-to-many against
> Enquiries, in preference to a multi-select picklist — their reasoning being
> that a growing list is cheaper as records than as field metadata, and that
> Zoho Analytics can then report sales/revenue per country or region
> relationally. Sandbox module:
> `https://crmsandbox.zoho.eu/crm/limitlessm97/tab/CustomModule2/custom-view/626421000019591121/list`
> That is exactly the target this kind wants, and it settles the picklist-vs-
> text decision in favour of "seeded from our region list". But **no `region`
> webhook URL was issued**, so there is still no route that fills or refreshes
> it: the module will accrete regions one enquiry at a time, keyed on whatever
> the embedded snapshots happen to carry, and a retired or re-slugged region
> still never reaches it. The build below is unchanged — chase the URL, and
> confirm `RES_ID` is the module's key before anything is seeded.

- **Severity:** 🟠 Gap (a retired region stays selectable in every Zoho
  dropdown until each villa/contact/enquiry embedding it happens to re-push —
  for a stable villa, never).
- **Source:** GAP-102 unit-1 review (2026-09-08). GAP-102 put `slug` /
  `is_active` / `iso3` on the wire; this is the freshness half it did not
  cover.
- **Files touched (when built):**
  - `django_res/integrations/services/zoho_flow.py` — `register_zoho_flow`
    call sites; `ZOHO_FLOW_KINDS`.
  - `django_res/properties/signals.py` — `_VILLA_CHILDREN` omits `Region` /
    `Country` (correctly: they are shared lookups, not villa children).
  - `django_res/integrations/management/commands/zoho_backfill.py` —
    `KIND_ORDER`.
  - `django_res/properties/views/geo.py` — `RegionViewSet` is a writable
    `ModelViewSet` exposing `slug` + `is_active`; admin registers both models.

### Problem

Region and country objects are only ever delivered as **snapshots inside**
villa / enquiry / quote / booking / contact pushes. No hook re-pushes anything
when a `Region` or `Country` row itself changes (`register_zoho_flow` is
called only for Person / Property / Enquiry / Quotation / Booking), so:

- Staff `PATCH /api/regions/{slug}` `{is_active: false}` → every payload Zoho
  already holds keeps `is_active: true` (and the old slug after a re-slug)
  until that parent is next saved.
- Regions with no villa never reach Zoho at all, so a dropdown "matching our
  values" (the 2026-09-08 Limitless ask: *"if we can just get a dump of
  those"*) cannot be assembled from embedded keys.
- "The same" region arrives in two shapes across records.

### Proposed fix

The GAP-102 ticket's own remedy for extras applies verbatim — a first-class
push, not a fan-out: `register_zoho_flow(Region, kind="region", …)` (country
rides inside the region payload, as today) with its own webhook URL from
Limitless on the GAP-096 coordination pattern, and a `region` stage at the
**front** of `zoho_backfill.KIND_ORDER` (organisation → **region** → contact
→ villa → enquiry → quote → booking). Fan-out (a Region save bumping every
villa in it) is the wrong shape: one region edit → N villa pushes.

Sequence the geo loader `DeletedBy`/orphan filtering (71 vs 57 legacy
regions, GAP-102 ticket text; now **GAP-107** §2) **before** the first
backfill of this kind, or the retired rows get pushed once and then have to be
retired again in Zoho.

### Acceptance

- Saving a `Region` (incl. `is_active` flip and re-slug) enqueues exactly
  one `region` push; saving a `Property` in it enqueues none extra. (test)
- `zoho_backfill` pushes `region` before any kind that embeds one. (test)
- A region with no villa reaches Zoho. (verified in the CRM — GAP-097)

### Dependencies

- **GAP-096** — same coordination pattern (URL from Limitless, env var,
  backfill ordering).
- **GAP-102** — resolved; supplies the keys this ticket keeps fresh.
- **CHECK-002** open decision (Countries of Interest picklist) — this is the
  "picklist we seed from our region list" option made maintainable.
