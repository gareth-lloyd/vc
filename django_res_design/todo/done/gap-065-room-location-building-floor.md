# GAP-065 — Room location: building + floor (and fix the lossy migration)

> **✅ RESOLVED (2026-07-05)** — shipped in 6 commits (model → API → loader →
> backfill → seeding → frontend) + this close-out. As proposed: `RoomPlacement`
> extended (cottage/bungalow/studio; "Annex"→"Annexe" label, value unchanged),
> new `RoomFloor` ladder, `Room.placement`/`floor` blank-able (`""`=unknown,
> MAIN_HOUSE default dropped), `RoomLoader` LEFT JOINs `VillaRoomsPlacement`
> and parses via `data_migration/placement_parsing.py` (typo/hyphen-tolerant;
> ordinal floors require a floor-context word; building picked by earliest
> text position; ambiguous rungs → `""`), reconcile row "Room placement
> (GAP-065)" (expected_gap=0 placeholder — recalibrate at first dry-run),
> `backfill_room_attrs` scans `placement_note` too, seed_dev
> `rooms_with_location` knob, FE floor select + sentinel placement select +
> grouped rooms list (headers only when ≥2 distinct groups; per-group DnD
> re-flattens and POSTs the full order). **Deviations:** raw string preserved
> in a dedicated `Room.placement_note` field (not a `vc_notes` append),
> API-writable so staff can clear it post-confirmation (FE editing deferred);
> existing rows keep their stored `main_house` (indistinguishable from
> deliberate; prod is reloaded by the fixed loader at cutover). **A2 owner
> steer unanswered** → ticket defaults shipped, pending confirmation recorded
> in `design/decisions.md`. Loader `--since` now alias-qualified
> (`r.UpdatedAt`); the same latent JOIN ambiguity exists in
> `PropertyContactAssignmentLoader` (`loaders/reservations.py`) — flagged,
> fix separately.

- **Severity:** Build + **data-loss bug** — answers **A2**, builds **Q-019**
- **Files:** `properties/enums.py` (`RoomPlacement` → repurpose + new `RoomFloor`),
  `properties/models/rooms.py` (`Room`), `data_migration/loaders/property_children.py`
  (`RoomLoader`), `frontend/.../RoomFormDialog.tsx`, room list grouping, room serializer
- **Depends on:** GAP-024 (fields optional). Land with GAP-064 (same model/form).

## Problem (two halves)

**(a) Model.** The loader encodes "first floor / ground floor / lower floor" as
text and manually keeps same-floor rooms adjacent in `sort_order`. Floor is not
data, so it can't group or sort.

**(b) Live data-loss bug.** Legacy `VillaRooms.PlacementId` → `VillaRoomsPlacement.Name`
is a free-text lookup that held **both** the floor **and** the building. The
current `RoomLoader` **never reads `PlacementId`** — it hardcodes
`placement = RoomPlacement.MAIN_HOUSE` for every row
(`property_children.py:41`). So on cutover **100% of legacy placement strings are
discarded** — a direct violation of "information must not be lost". This ticket
is the fix.

## Legacy evidence (production dump)

`VillaRoomsPlacement` is a two-axis field overloaded into one free-text box.
Distinct-concept frequencies from the dump:

**Floor axis:**
```
Ground floor  308   First floor 303   Second floor  25
Lower level    15   Ground level 14   Lower ground  10
Upper floor     6   Upper level   2   Mezzanine/Basement 1 each
```
**Building axis:**
```
Main house 78   Guest house 22   Annexe 17   Cottage 12
Bungalow    5   Studio     4   Loft   3   Pool house 2   Wing 2
```
**...plus facts crammed into the same string** (these belong in GAP-064 / beds,
not location): `"First floor. Ceiling fan"`, `"Ground floor. Mini fridge, safe"`,
`"First floor - King, hairdryer"`, `"Ground floor. Mosquito nets"`,
`"First floor. Superking bed."`, `"First floor. Wifi"`, and typos (`"First foor"`).

Two conclusions:
- Location genuinely has **two axes** (which building, which floor). A single
  field cannot express "first floor **of the guest house**" — common on these
  multi-building estates.
- The current `RoomPlacement` enum (`main_house/guest_house/pool_house/annex/other`)
  already captured the **building** axis — but the **floor** axis was dropped
  entirely, and the loader doesn't even populate the building one.

## Proposed model (opinionated)

Keep `RoomPlacement` as the **building/structure** axis (extend it), and add a
separate **floor** enum:

```python
class RoomPlacement(models.TextChoices):     # building/structure — extend existing
    MAIN_HOUSE  = "main_house",  "Main house"
    GUEST_HOUSE = "guest_house", "Guest house"
    POOL_HOUSE  = "pool_house",  "Pool house"
    ANNEX       = "annex",       "Annexe"
    COTTAGE     = "cottage",     "Cottage"      # 12 in legacy
    BUNGALOW    = "bungalow",    "Bungalow"     # 5
    STUDIO      = "studio",      "Studio"       # 4
    OTHER       = "other",       "Other"

class RoomFloor(models.TextChoices):         # A2 fixed ladder
    LOWER_GROUND = "lower_ground", "Lower ground"
    GROUND       = "ground",       "Ground"
    FIRST        = "first",        "First"
    SECOND       = "second",       "Second"
    THIRD_PLUS   = "third_plus",   "Third or above"
    # "" (blank) = unknown

# on Room:
placement    = CharField(choices=RoomPlacement, blank=True)   # building; drop the MAIN_HOUSE default
floor        = CharField(choices=RoomFloor, blank=True)       # "" = unknown
```

**Design calls:**
- **Fixed floor ladder, not free numbering.** The data tops out at second floor;
  `THIRD_PLUS` catches the rare rest. Free numbering is exactly what produced the
  current mess (`"First foor"`, `"First floor. Superking bed"`). A2 recommends the
  ladder — the data backs it.
- **Two fields, not one.** The building axis is real and frequent; keep it
  first-class rather than smuggling "Guest house" into the floor picker.
- **Drop the `default=MAIN_HOUSE`.** Defaulting building to "main house" is the
  same lie as a `False` boolean — leave blank when unknown.
- **Loft / Wing / Roof terrace** don't fit cleanly → `OTHER` + the raw string
  preserved (see translation). Don't over-fit the enum to one-off values.

## Legacy translation (no information loss) — the core of this ticket

Rewrite `RoomLoader.transform` to actually read placement and split it losslessly:

1. Extend `legacy_query` to `JOIN VillaRoomsPlacement p ON p.Id = r.PlacementId`
   and select `p.Name AS PlacementName`.
2. **Preserve the raw string, always.** Store the original `PlacementName` in a
   new `Room.placement_note` (or append to `vc_notes` as
   `"[placement] <original>"`). This is the no-loss guarantee: even if parsing is
   imperfect, the exact legacy text survives and is human-recoverable.
3. **Parse into `placement` + `floor`** with a small deterministic matcher
   (case-insensitive, typo-tolerant for the two known typos):
   - `"ground floor"/"ground level"` → `floor=GROUND`
   - `"lower ground"` → `LOWER_GROUND`; `"first"` → `FIRST`; `"second"` → `SECOND`
   - `"third"+` → `THIRD_PLUS`
   - `"upper floor"/"upper level"` / `"lower level"` → **ambiguous** — leave
     `floor=""` and rely on the preserved raw string (owner steer 2 below).
   - building words (`guest house`, `annexe`, `cottage`, `bungalow`, `studio`,
     `pool house`) → set `placement`; default `MAIN_HOUSE` **only** when a floor
     matched but no building word is present (a bare "First floor" is implicitly
     the main house).
4. **Crammed facts are not lost, just re-homed later.** GAP-064 / GAP-066 backfill
   passes can scan the same preserved string for `ceiling fan`, `safe`,
   `king bed`, etc. Until then the raw string holds them — nothing is dropped.
5. Add a `reconcile_legacy` row: legacy rooms with a non-null `PlacementId` vs.
   rooms migrated with either a parsed `floor`/`placement` **or** a preserved raw
   note = must be 100%. Expected parse-rate (floor recognised) ≈ the 90%+ that are
   ground/first/second; the remainder are preserved-raw, not lost.

## Frontend

- `RoomFormDialog.tsx`: building select + floor select (both optional, blank =
  "not set"). Show the preserved `placement_note` as read-only helper text on
  migrated rooms until a human confirms the split.
- **Rooms list groups by building → floor** (A2's promised payoff), replacing the
  manual `sort_order` adjacency. Keep `sort_order` as the within-group tiebreak.

## Owner steer (A2)

1. **Confirm the floor ladder rungs:** Lower ground / Ground / First / Second /
   Third+. Good enough?
2. **"Upper floor" / "Lower level"** appear in the data — map `Upper→First`?
   Treat as `Other`? Or add rungs? (Recommend: leave to `THIRD_PLUS`/blank +
   raw note; not worth a rung each.)
3. **Building + floor as two fields** (recommended) vs. one — confirm.

## Next steps

1. Extend `RoomPlacement`, add `RoomFloor`, add `Room.floor` (+ `placement_note`);
   migration; drop the building default.
2. **Fix `RoomLoader`** — join placement, preserve raw, parse two axes; reconcile row.
3. Serializer + `schemas.ts` (both optional) + form selects.
4. Rooms-list grouping by building→floor.

## Acceptance

- No legacy `PlacementId` is dropped: every room with a placement lands with a
  parsed axis **or** a preserved raw note (reconcile = 100%).
- `Room` has orthogonal `placement` (building) + `floor` (ladder).
- Rooms list groups by building→floor automatically; `sort_order` still respected.
- A room saves with neither set (GAP-024).
</content>
