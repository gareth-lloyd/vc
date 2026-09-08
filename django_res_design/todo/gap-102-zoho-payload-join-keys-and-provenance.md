# GAP-102 — Zoho payloads carry no join key for extras, no extras catalogue, no keyable geo, and no provenance

- **Severity:** 🟠 Gap (four un-keyable/unattributable surfaces in the
  outbound push; item 2 blocks Limitless' quoting model, items 1 and 3 make
  their dropdowns and product matching name-based, item 4 is why an
  unexplained webhook execution cannot be attributed to anyone).
- **Source:** 2026-09-08 Limitless call (Greg + Ben). Four asks in one
  sitting, all the same shape: *"we can see the data, we can't key on it."*
  Extras "don't have a res ID, but they still need to be like a full
  product… in terms of the quoting"; "for the regions and countries, if we
  can just get a dump of those"; "we get quite a few of the webhooks come
  through without any payload in them".
- **Files touched (when built):**
  - `django_res/reservations/services/zoho_payload.py:323` —
    `_extras_payload`, the booking `extras[]` builder.
  - `django_res/reservations/services/zoho_payload.py:155` and
    `django_res/properties/services/zoho_payload.py:78` — the two
    deliberately byte-identical `_region_payload` copies (the module
    docstring at `properties/services/zoho_payload.py:29` records the
    duplication as intentional; **change both**).
  - `django_res/properties/services/zoho_payload.py:213` —
    `build_property_payload`, if the catalogue lands embedded.
  - `django_res/integrations/tasks.py:102` — the single `httpx.post`, where
    the envelope marker and header go.
  - Read-only context: `django_res/pricing/services/quote.py:47`
    (`AppliedExtra.extra_id`, already in every snapshot),
    `django_res/pricing/models/extra.py:11` (`Extra`, property-scoped),
    `django_res/properties/models/geo.py:8` (`Country`/`Region`).

## Problem

### 1. `extras[]` entries have no identity

`_extras_payload` emits four keys per row — `label`, `amount`,
`commissionable`, `category` — and nothing else. The CRM's only handle on an
extra is its display label, so a renamed extra is a new product, two villas'
"Cleaning" are indistinguishable, and a re-push cannot update the row it
wrote last time. This is the direct cause of the open **CHECK-004** decision,
where every extras row points at one hardcoded `extras_product_id` with the
label and category concatenated into `Description` free text.

The identity already exists and is simply not forwarded: the engine writes
`extra_id` into the priced snapshot (`pricing/services/quote.py:47`) and
manual lines are `BookingChargeItem` rows with their own primary key. Two
distinct id spaces feed one array, so a bare `RES_ID` is not enough — the
entry must say which space it came from.

### 2. Nothing ever pushes the extras catalogue

The villa payload deliberately carries no pricing data
(`properties/services/zoho_payload.py:19`: *"Deliberately NO availability or
pricing data — res stays the sole source"*), and there is no `extra` push
kind. The consequence Limitless hit: an extra becomes visible to Zoho only
when a booking that used it arrives, which is far too late to quote from.
For "the villa plus its extras" to be listable on a quote — the structure Ben
described, options as records in a linked module — the products have to exist
*before* the quote references them.

The scoping matters for the CRM model and is easy to get wrong: `Extra` is
**property-scoped** (`pricing/models/extra.py:14`). "Cleaning" on Villa A and
"Cleaning" on Villa B are two rows with two ids, so a one-product-per-name
catalogue silently merges them.

### 3. Geo sub-objects cannot be keyed

`_region_payload` sends `RES_ID`/`id`/`name` for the region and
`RES_ID`/`id`/`name`/`iso2` for the country. Missing: the region `slug`,
`is_active` on both, and country `iso3`. Limitless are rebuilding their
dropdowns to match our values, so the keys we omit are the ones they fall back
to matching by name — which is exactly what breaks when a region is tidied up.
`is_active` is the one with no substitute: without it a retired region cannot
be hidden from new selections while staying readable on historic records.

Related but **not** in this ticket: the loaders that will populate those
tables do not filter `DeletedBy`, so a cutover run imports 71 legacy region
rows instead of 57, including ten live-but-orphaned rows hanging off deleted
countries ("Villa Villa Region", "Test Regions", London/England, three Indian
regions). That is a data-load defect and needs its own ticket — but it lands
in the same dropdowns, so sequence it first.

### 4. A push carries no provenance

`httpx.post(url, json=payload)` sends the object payload and nothing else: no
environment marker, no source marker, no dispatch id. Two costs.

The immediate one is the empty-payload executions Limitless are seeing. We
have exactly one POST site and it always sends a JSON body, so those
executions are not from the push path — most likely the Flow builder's own
Test button or a browser GET on the webhook URL. Right now that is an
assertion; a marker makes it checkable, because anything without
`_meta.source` is provably not ours.

The standing one is that dev and live Flows now run side by side against the
same CRM org, distinguished only by which URL is configured
(`villacollective/settings/base.py:216`). A payload in a Flow log is
currently indistinguishable from a payload sent by the other environment.

## Proposed fix

**1 — identity on extras rows.** Add to every `_extras_payload` entry:
`RES_ID`, `source` (`"extra"` | `"charge_item"`), and `currency` (the
booking's code — every entry is in it). Signed amounts stay verbatim; a
negative line is a credit. The array stays informational — every entry is
already inside `financials.total_gross` and Zoho must not re-add it — and the
docstring should keep saying so.

**2 — the catalogue, once a shape is chosen.** Two options, and this needs a
decision before code:

- *(a) Embedded in the villa payload.* An `extras[]` block on
  `build_property_payload` with id, name, category, calc, amount, currency,
  `is_mandatory`, `commissionable`, `is_active`, the `applies_from`/`_to`
  window and the party limits. Cheapest to build, no new webhook, and it
  keeps villa and extras atomically consistent. Cost: it crosses the "no
  pricing in the villa payload" line we drew on purpose, and every extra edit
  re-pushes the whole villa.
- *(b) A sixth push kind.* `register_zoho_flow(Extra, kind="extra", …)` with
  its own webhook URL, mirroring GAP-096's shape. Keeps the boundary, gives
  extras their own lifecycle, and one edit is one push. Cost: another Flow
  and another URL from Limitless, so a coordinated landing.

Recommendation: **(b)**, for the same reason GAP-096 rejects a villa-child
bump receiver — an extra edit should not fan out a villa push. But (a) is
defensible if Limitless would rather not stand up another endpoint, and the
decision is theirs as much as ours.

Either way the product key is the **(villa, extra) pair**, not the name.

**3 — geo keys.** Add `slug` and `is_active` to the region object and `iso3`
plus `is_active` to the country object, in both copies. Purely additive.

**4 — provenance envelope.** Wrap or annotate every push with
`_meta: {source: "res", env, pushed_at, sync_record_id, kind}` and send an
`X-Res-Env` header alongside. Prefer the **sibling key** over a wrapper
object: a wrapper renames the root for all five existing Flows and would
break every mapping Limitless has already written. `env` reads from settings,
not from the URL.

## Acceptance

- Every `extras[]` entry carries `RES_ID`, `source` and `currency`; a
  snapshot extra and a charge item with the same numeric id are
  distinguishable. (test)
- Two villas' identically-named extras produce different `RES_ID`s on the
  wire. (test)
- The extras catalogue reaches Zoho before any booking references it —
  asserted by ordering in `zoho_backfill` if (b), by the villa push if (a).
  (test)
- An extra edit produces exactly one push, not one per booking that used it.
  (test — the point of option (b))
- Region objects carry `slug` + `is_active`, country objects `iso3` +
  `is_active`, in **both** builders. (test, one per module — the duplication
  is deliberate and a single test would let one copy drift)
- Every outbound POST carries `_meta.source == "res"` and a resolvable
  `env`; no root key of an existing payload moves. (test)
- A `zoho_send_sample` run is attributable end-to-end: every Flow execution
  it causes carries the marker, and any execution without one is provably
  from another source. (verified against the sandbox, not from `IN_SYNC` —
  GAP-097)

## Dependencies

- **CHECK-004 "Open decision — extras reporting"** is closed by items 1+2:
  the call answered it (extras are full products with stable res ids), so
  this ticket is our half and CHECK-004's remaining half is their mapping.
  **CHECK-005** carries the same decision for quotes.
- **GAP-096** — if the catalogue lands as option (b), it needs a webhook URL
  from Limitless on exactly the coordination pattern GAP-096 already
  describes, and the backfill ordering grows a step: organisation → contact →
  villa → **extra** → enquiry → booking.
- **GAP-097** — none of the acceptance criteria above can be verified from
  our `SyncRecord` status; all Zoho-side checks read the CRM.
- **GAP-098** — `RES_ID` on extras is the same class of fix (a stable key on
  the wire) but a different key space; don't fold them.
- Geo loader soft-delete/orphan filtering is **not** in scope here and needs
  its own ticket, sequenced ahead of any production villa push.
- No dependency on the dev → live endpoint switch: that is five env vars
  (`ZOHO_FLOW_WEBHOOK_*`) and no code, and all four items here are additive,
  so they can land on the dev endpoints and be re-verified after cutover.
