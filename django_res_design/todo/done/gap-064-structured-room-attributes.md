# GAP-064 — Structured room attributes (admin-editable attribute catalog)

> **✅ RESOLVED (2026-07-05)** — shipped on `feat/gap-064` in 5 commits
> (`9868d55`, `cfacca6`, `a8a1778`, `a7bd5f1`, `e821aee`), merged to local
> `main` (unpushed).
> - **Facets**: `Room.ensuite_type` (shower/bath/both) + `Room.access`
>   (inside/outside), blank-able enum columns (`""` = unknown), with a DB
>   CheckConstraint `room_ensuite_type_implies_is_ensuite`; the serializer
>   keeps the pair coherent in both directions.
> - **Amenities**: `RoomAttribute` catalog (name, unique slug, icon,
>   sort_order, is_active, nullable `implies_property_feature` SET_NULL) +
>   `RoomAttributeAssignment` (room CASCADE via `attribute_links`, attribute
>   PROTECT, optional note, unique (room, attribute)); Django-admin curation;
>   9 starter rows seeded by migration `0027` via the re-invocable
>   `sync_room_attributes()`; audit-tracked per FG-017; seed_dev
>   `room_attributes` stage (knob `attributes_per_room`).
> - **API**: facets + `attribute_links` full-list sync on `RoomSerializer`
>   (absent on PATCH leaves links alone; retired links resubmitted are kept —
>   the B1 review blocker); read-only anon `/room-attributes` catalog
>   endpoint (serves inactive rows; ConfigurablePageSizePagination).
> - **Frontend**: RoomFormDialog facet selects + data-driven amenity tick
>   list (active ∪ assigned, retired badged but still ticked), per-tick note;
>   RoomsTab chips; en+el i18n; MSW default handlers.
> - **Backfill**: `backfill_room_attrs` (positives-only keyword pass,
>   `--dry-run`, idempotent, re-syncs implications) — CUTOVER.md §6b.
>
> **Deliberate deviations from the sketch below**: assignment
> `related_name` is `attribute_links` (mirrors `feature_links`; keeps the
> serializer field name free), not `attributes`; implication linking is
> set-if-NULL and deferred to post-load re-sync (Features are not
> migration-seeded, so slug lookups at migrate time always miss); the
> ticket's `10-decisions.md` filename is `design/decisions.md`.
> **A1 owner steer was NOT answered** — ticket defaults shipped (ensuite
> trio; 9 starter rows; sea_view→sea-view implication; wheelchair stays
> NULL until an accessibility Feature exists). All of it is admin-editable
> data — recorded as pending owner confirmation in `design/decisions.md`.
> **Moved, not lost**: placement-text backfill source → GAP-065 (re-run
> `backfill_room_attrs` when it lands); derivation service → GAP-067;
> FE catalog admin screen → Django admin suffices for now.


- **Severity:** Build (with one vocabulary decision) — answers **A1**, builds **Q-019**
- **Files:** `properties/models/rooms.py` (`Room`, new `RoomAttribute`,
  `RoomAttributeAssignment`), `properties/enums.py` (new `EnsuiteType`,
  `RoomAccess`), admin surface for `RoomAttribute`, room serializer,
  `frontend/.../RoomFormDialog.tsx`, `frontend/.../schemas.ts`,
  seeding (attribute catalog), `data_migration/loaders/property_children.py`
- **Depends on:** GAP-024 (attributes optional — a room saves with just a name),
  GAP-065 (same model/form — land together), GAP-067 (consumes the derivation bridge)

## Problem

The loader types the same room facts as prose in a memorised fixed order —
"ensuite shower", air con, then sea view / balcony / terrace — into
`website_description`. Nothing enforces or queries it, and the same fact
(e.g. wheelchair access) gets entered in three places from memory.

The current `Room` model keeps only `is_ensuite` (bool); every other attribute
lives in free text. This ticket structures them **without** widening the schema
one boolean column at a time, because the owner expects the attribute set to
change and unexpected attributes to arise.

## Two kinds of "attribute" — modelled two ways

A design distinction that drives everything below:

| Kind | Examples | Shape |
|---|---|---|
| **Closed, single-valued facet** | ensuite type (shower/bath/both), access (inside/outside) | **enum column** on `Room` |
| **Open-ended presence/absence amenity** | aircon, ceiling fan, sea view, balcony, terrace, wheelchair, in-room safe, hairdryer, fridge | **admin-editable tag** (`RoomAttribute`) |

Facets are validated classifications with a fixed set of states — columns are
correct. Amenities are an open list that will grow — a widening column set is the
wrong shape (5 touch-points of ceremony per new attribute, developer-only). They
get a **room-scoped reference catalog**, deliberately **separate** from the
property `Feature`/services taxonomy (different bounded context: no
`service_type`, no pricing/collections coupling, no category mismatch).

## Legacy evidence (not a guess)

The intended vocabulary already exists in the legacy **bedroom exhibit form**
(`Template/ExhibitForm_Bedroom_Details.html`) — the DB schema is a stripped-down
subset of it:

| Exhibit field | In legacy DB? | This ticket |
|---|---|---|
| ENSUITE — NONE / BATH / SHOWER / BATH WITH SHOWER / BATH AND SHOWER | only a bool (`IsEnsuit`) | `ensuite_type` **facet column** |
| INSIDE ACCESS (checkbox) | no | `access` **facet column** |
| AIR CON (checkbox) | no (faked at property level) | `RoomAttribute` "aircon" |
| CEILING FAN (checkbox) | no | `RoomAttribute` "ceiling_fan" |
| MOSQUITO NET/SCREEN (checkbox) | no | **internal** → stays `vc_notes` |

Facts repeatedly **crammed into free text** in the production dump confirm what
Bryony actually types: `ceiling/overhead fan`, `hairdryer`, `mini-fridge`, `safe`,
`dressing room`, `wifi`. Air-con is faked at property level as **five** duplicate
features — direct evidence the open-ended tag set (not a fixed column) is the
right primitive. "Balcony" has **no** structured representation (0 features, 234
free-text mentions).

## Proposed model (opinionated)

### Facets — enum columns on `Room`

```python
class EnsuiteType(models.TextChoices):
    SHOWER = "shower", "Shower"
    BATH   = "bath",   "Bath"
    BOTH   = "both",   "Bath & shower"

class RoomAccess(models.TextChoices):
    INSIDE  = "inside",  "Inside access"
    OUTSIDE = "outside", "Separate outside access"

# on Room:
ensuite_type = CharField(choices=EnsuiteType, blank=True)  # "" = unknown; refines is_ensuite
access       = CharField(choices=RoomAccess, blank=True)
```

`is_ensuite` (bool) stays; `ensuite_type` refines it when known. `access` reuses
the legacy "inside access" concept (= A1's "outside access", opposite default).

### Amenities — admin-editable `RoomAttribute` catalog + through model

```python
class RoomAttribute(TimestampedModel):
    """Admin-curated catalog of per-room amenity tags. SEPARATE from the property
    `Feature` taxonomy. A new attribute is a data row a curator adds — no
    migration, no serializer/schema/FE-field change."""
    name        = CharField(max_length=64)          # display label, editable
    slug        = SlugField(unique=True)            # stable machine key (code/backfill/tests)
    description = TextField(blank=True)
    icon        = CharField(max_length=64, blank=True)
    sort_order  = PositiveIntegerField(default=0)
    is_active   = BooleanField(default=True)         # retire via deactivate, never delete-in-use
    # The GAP-067 bridge, data-driven: any room carrying this attribute derives
    # this property-level Feature. NULL = a room-only fact (most of them).
    implies_property_feature = ForeignKey(
        "properties.Feature", null=True, blank=True,
        on_delete=SET_NULL, related_name="+",
    )

    class Meta:
        ordering = ["sort_order", "name"]

class RoomAttributeAssignment(models.Model):
    room      = ForeignKey(Room, related_name="attributes", on_delete=CASCADE)
    attribute = ForeignKey(RoomAttribute, related_name="+", on_delete=PROTECT)
    note      = CharField(max_length=200, blank=True)  # per-room nuance: "sea view from balcony only"

    class Meta:
        unique_together = ("room", "attribute")
```

**Design calls:**
- **Reference table, not an enum.** The owner wants room attributes editable
  without a developer/deploy — so the vocabulary is data (curated in an admin
  screen), and the room picker renders whatever is `is_active`. New attribute =
  one row.
- **Separate catalog from property `Feature`.** Different bounded context. Room
  amenities carry none of the services/pricing/collections/`service_type`
  baggage; the two vocabularies evolve independently. A handful of concepts
  (sea view, aircon) legitimately exist at *both* grains — "this room has a sea
  view" vs. "this villa is marketed for its sea views" are different assertions,
  which is exactly why they are different rows joined by an explicit bridge, not
  one shared row.
- **`implies_property_feature` makes the GAP-067 bridge data-driven.** A curator
  ticks "wheelchair implies the villa accessibility feature" on the catalog row;
  no hardcoded map. NULL for room-only facts (fan, safe, balcony).
- **`slug` is the stable key**; `name` is the editable label. Code, backfill and
  tests key on slug so relabelling never breaks them.
- **`PROTECT` + `is_active`**: a catalog row in use can't be deleted, only
  retired — assignments never dangle.
- **Optional per-assignment `note`** mirrors the property feature's per-villa
  `Description` override, for nuance ("sea view from the balcony only").
- **Presence semantics** (accepted trade-off): present = yes, absent = not
  claimed. No explicit "confirmed absent" — fine for search/marketing, and the
  conservative default for accessibility.
- **Mosquito screens stay internal** (`vc_notes`) — unadvertisable per A1; not a
  catalog row.

## Legacy translation (no information loss)

Attributes live in prose today, so **prose is preserved and the catalog is
forward-looking enrichment**:

1. `website_description` / `vc_notes` migrate **unchanged** — zero loss.
2. The `RoomAttribute` catalog is **seeded** (new curated rows — not migrated from
   a legacy table); `ensuite_type` / `access` default to `""` (unknown).
3. **Optional best-effort backfill** (`--backfill-room-attrs`, positives only): a
   keyword pass over `website_description` + the preserved legacy placement string
   (GAP-065) creates `RoomAttributeAssignment` rows for confident matches
   (`"air con"` → aircon, `"sea view"` → sea_view, `"en-suite shower"` →
   `ensuite_type=SHOWER`). Never infers an absence. Source text is retained, so a
   miss loses nothing — it's convenience behind a flag + a reconcile count, not a
   correctness dependency.

## Frontend

- `RoomFormDialog.tsx`: fetch the active `RoomAttribute` catalog and render it as
  a tick-box list (grouped by `sort_order`) — **data-driven, so new attributes
  appear with no FE change**. Tick = create assignment; untick = delete. Optional
  inline `note` on a ticked attribute. Two small selects for `ensuite_type` /
  `access`.
- `schemas.ts`: attribute assignments + facets all optional (mirror serializer;
  no schema stricter than backend — GAP-024).
- Room list/detail: render assigned attributes as an icon/label row; unset =
  omitted (A3 keeps the *public* site prose-only — this is the internal view).
- **Admin surface** for `RoomAttribute` (Django admin is enough to start;
  analogous to the property `02-administration/product-taxonomy` screen).

## Owner steer (A1)

1. **Ensuite shower/bath/both** — confirm Bryony tracks the distinction (legacy
   only stored yes/no). If not, ship `is_ensuite` alone, drop `ensuite_type`.
2. **Seed catalog** — confirm the starter `RoomAttribute` rows: aircon, ceiling
   fan, sea view, balcony, terrace, wheelchair, in-room safe, hairdryer, mini
   fridge. (All frequently hand-typed in the dump.) Which imply a property
   feature? (wheelchair → accessibility; sea view → sea-views.)
3. **Interconnecting rooms** — A1 floats it, but it barely appears; add it as a
   catalog row later if wanted, no schema change needed.

## Next steps

1. Take the A1 decision (owner steer 1–2); record in `10-decisions.md`.
2. Add `EnsuiteType`/`RoomAccess` + `Room.ensuite_type`/`access`; add
   `RoomAttribute` + `RoomAttributeAssignment`; migration.
3. Seed the starter catalog (with `implies_property_feature` set where agreed).
4. Serializer + `schemas.ts` + data-driven `RoomFormDialog` tick-box list; admin
   surface for the catalog.
5. Optional `--backfill-room-attrs` positives-only pass + reconcile row.
6. Hand the derivation bridge to GAP-067.

## Acceptance

- Facets (`ensuite_type`, `access`) are enum columns; amenities are `RoomAttribute`
  rows — a new amenity is a data row, no migration/serializer/FE change.
- `RoomAttribute` catalog is admin-editable; in-use rows can't be hard-deleted.
- `website_description`/`vc_notes` migrate byte-for-byte (reconcile: 0 loss).
- A room still saves with no attributes set (GAP-024).
- Public website output unchanged (A3) unless the owner opts in.
</content>
