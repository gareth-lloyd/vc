# WordPress external-ID backfill — investigation & decision

**Status: not built. This is a decision note, not a spec to implement blindly.**

The Zoho external-ID backfill ships (`loaders/integrations.py`
`SyncRecordZohoLoader`, verified by `reconcile_legacy --integrations`). The
WordPress side is deliberately *not* built yet because, unlike Zoho, it does
not fit the current `SyncRecord` model and several of its source "modules"
have no 1:1 Django row. This note records what the legacy data looks like,
the model gap, the open questions a cutover dry-run must answer, and the
options — so the call is made on evidence, not on the design doc alone.

## Why Zoho fits but WordPress doesn't

`integrations.SyncRecord` is keyed `(content_type, object_id, provider)` and
has **no `provider_instance` and no `meta` field** (see
`integrations/models/sync_record.py`). Zoho is single-tenant: one external id
per (row, provider), so it fits cleanly.

WordPress is **multi-site**: the same villa is published to several WP sites,
each with its own post id and URL. The design (`08-integrations.md`) models
this as `SyncRecord(provider=WORDPRESS_SITE, provider_instance=<SiteId>)`,
with `provider_instance` **in the uniqueness key**. The current model can't
represent two WP rows for the same (villa) target — the second collides on
`unique(content_type, object_id, provider)`. So WordPress needs a model +
migration change before any loader can run.

## Legacy data shape (verified in `ResSystem/`)

External ids live in three places:

| Legacy source | Column(s) | Notes |
|---|---|---|
| `VillaBooking` | `BookingUrl` | The WP booking-confirmation URL. Legacy stores only the URL, not the post id. |
| `VillaConcierge` | `Slug` | Per-booking concierge page slug. |
| `VillaSyncDetail` | whole table | The normalised per-site sync table — the real source of truth. |

`VillaSyncDetail` columns (per `ResSystem/Database/Data/VillaSyncDetail.cs`):

- `SiteId` (int) → intended `SyncRecord.provider_instance`
- `ModuleId` (int) → which kind of thing was synced (see map below)
- `ModulePrimaryId` (int) → the legacy row id within that module
- `SyncId` (int?) → the WordPress post id (nullable)
- `VillaUrl` (string?) → the WP URL
- `Process` (string?) → free-form legacy status
- `CreatedAt` / `UpdatedAt`

### `ModuleId` → entity (legacy `ResModule`, `CommonProperties.cs:77`)

```
BOOKING            = 1     COUNTRY            = 10    REGION             = 20
FEATURE            = 30    COLLECTION         = 40    VILLA              = 50
VILLA_ALTERNATIVE  = 60    VILLA_RENT_TOGATHER= 70    VILLA_ROOMS        = 80
VILLA_FEATURES     = 90    VILLA_COLLECTION   = 100   VILLA_LOCATION     = 110
VILLA_IMAGES       = 120   VILLA_DESCRIPTION  = 130   FLYWIRE            = 140
```

**Key finding:** only some modules map to a 1:1 Django row that can carry a
generic-FK `SyncRecord`:

- Clean targets: `VILLA`→`Property`, `BOOKING`→`Booking`, `COUNTRY`→`Country`,
  `REGION`→`Region`, `FEATURE`→`Feature`, `COLLECTION`→`Collection`,
  `VILLA_ROOMS`→`Room`, `VILLA_IMAGES`→`PropertyImage`.
- **No clean target:** `VILLA_DESCRIPTION` / `VILLA_ALTERNATIVE` /
  `VILLA_RENT_TOGATHER` / `VILLA_LOCATION` / `VILLA_FEATURES` /
  `VILLA_COLLECTION` are facets of a villa (a description, a m2m membership),
  not standalone rows — there is no obvious `(content_type, object_id)` to
  point a `SyncRecord` at. `FLYWIRE` is a payment concern, not WP.

This is the crux: a faithful WP backfill needs a per-`ModuleId` resolution
strategy, and for several modules that strategy is "there is no row" —
exactly the kind of decision that must not be guessed.

## Questions the cutover dry-run must answer

Run these against a real `LEGACY_DATABASE_URL` (mssql) during the dry-run.
They are cheap and read-only.

```sql
-- 1. How many sites are actually in play?
SELECT COUNT(DISTINCT SiteId) AS sites,
       COUNT(*)               AS rows_total
FROM VillaSyncDetail;

-- 2. Volume per module — which modules are even used, and how heavily?
SELECT ModuleId, COUNT(*) AS rows, COUNT(SyncId) AS with_post_id
FROM VillaSyncDetail
GROUP BY ModuleId
ORDER BY rows DESC;

-- 3. Multi-site fan-out: is the same (module,row) really synced to >1 site?
--    If this is ~0, multi-site is moot and Option B is safe.
SELECT TOP 20 ModuleId, ModulePrimaryId, COUNT(DISTINCT SiteId) AS sites
FROM VillaSyncDetail
GROUP BY ModuleId, ModulePrimaryId
HAVING COUNT(DISTINCT SiteId) > 1
ORDER BY sites DESC;

-- 4. Rows that carry a usable post id (the thing worth preserving).
SELECT COUNT(*) AS with_post_id
FROM VillaSyncDetail
WHERE SyncId IS NOT NULL;

-- 5. Bookings with a URL but NO VillaSyncDetail row (the defensive case
--    08-integrations.md warns about — legacy didn't always write the table).
SELECT COUNT(*) AS booking_urls_without_syncdetail
FROM VillaBooking b
WHERE b.BookingUrl IS NOT NULL AND LTRIM(RTRIM(b.BookingUrl)) <> ''
  AND NOT EXISTS (
    SELECT 1 FROM VillaSyncDetail s
    WHERE s.ModuleId = 1 /* BOOKING */ AND s.ModulePrimaryId = b.Id
  );
```

The `reconcile_legacy --integrations` WordPress section already prints (1),
the BookingUrl volume, and total `VillaSyncDetail` rows as an informational
surface, so the operator sees the magnitude even before this deeper dig.

## The decision

### Option A — extend the model, build the loader (full fidelity)

1. Migration on `SyncRecord`: add `provider_instance = CharField(blank=True,
   default="")` and `meta = JSONField(default=dict)`; change the unique
   constraint to `(content_type, object_id, provider, provider_instance)`
   (Zoho keeps `provider_instance=""`, so existing Zoho rows are unaffected).
2. `SyncRecordWordPressLoader`: iterate `VillaSyncDetail`, resolve
   `ModuleId`→model and `ModulePrimaryId`→local pk via `legacy_id`, upsert
   `SyncRecord(provider=WORDPRESS_SITE, provider_instance=str(SiteId),
   external_id=str(SyncId), external_url=VillaUrl,
   meta={"legacy_process": Process})`. Backfill `BookingUrl` / concierge
   `Slug` for rows with no `VillaSyncDetail` entry.
3. Decide, per the "no clean target" modules above, to **skip** them
   (recommended — they re-sync from the parent villa) and record the skip in
   the loader report.
4. Promote the WP section of `reconcile_legacy --integrations` from
   informational to enforced.

Cost: one model migration touching a shared integrations table + a loader +
tests. Justified **only if** dry-run query (3) shows real multi-site fan-out
and (4) shows a meaningful number of post ids worth preserving.

### Option B — descope WP multi-site for the M1 capture

If queries (3)/(4) show little/no fan-out and few post ids (likely, since WP
re-publish is cheap and the M1 site list may be a single site), do **not**
change the model. Instead, capture only what's losslessly representable now:
store the single most-recent `(booking, BookingUrl)` per booking as
`SyncRecord(provider=WORDPRESS_SITE, external_id="", external_url=BookingUrl)`
(no `provider_instance` needed for one site), and accept that historical
multi-site post ids are not preserved — WP re-publish regenerates them.

Cost: tiny. Risk: if WP push later needs the exact historical post id to
UPDATE-in-place, those are gone. Mitigated by the fact that the **outbound
WP sync engine is itself unbuilt** (v1.1+), so there is runway to revisit.

### Recommendation

**Defer the choice to the dry-run output of query (3)/(4), and default to
Option B unless the data shows real multi-site fan-out.** The whole WP
outbound path is v1.1+, so the only thing genuinely lost by deferring is the
historical post ids — and only if they turn out to exist in quantity *and*
the future WP sync turns out to need them. Building Option A now (a migration
on a shared table) ahead of that evidence is premature. Capture Zoho cleanly
now (done); make the WP call with live counts in hand.
