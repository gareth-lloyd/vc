# GAP-066 — Bed size fidelity + bed-type vocabulary

- **Severity:** Build (with one owner steer) — surfaced from legacy, not in A1/A2
- **Files:** `properties/models/rooms.py` (`RoomBeds`), `properties/enums.py`
  (new `BedSize`), `data_migration/loaders/property_children.py` (`RoomLoader`),
  `frontend/.../RoomFormDialog.tsx`, room serializer
- **Depends on:** GAP-065 (bed sizes are among the facts crammed into the legacy
  placement string; the same preserved-raw text feeds this backfill)

## Problem

A1 says bed types/counts are "already structured" — and counts are (`RoomBeds`
has 7 nullable ints). But **bed size is not captured anywhere structured**, and
the legacy data shows it is a fact the loader actively records — just with
nowhere to put it, so it leaks into free text.

## Legacy evidence

- The bedroom **exhibit form** has a dedicated **BED SIZE** field next to BED
  TYPE (`Template/ExhibitForm_Bedroom_Details.html`) — the intended model always
  had bed size; the DB just never implemented it.
- The production dump shows sizes hand-typed into the wrong fields:
  `"First floor. Superking bed."`, `"First floor - King, hairdryer"`,
  `"Ground floor. King bed."`, `"First floor. Master bedroom."`. These are in the
  **placement** string because there was no bed-size field.
- Legacy bed **type** is 7 denormalised count columns (`BedDouble`, `BedTwinDouble`,
  `BedTwin`, `BedSingle`, `BedBunk`, `BedSofa`, `BedChildrens`) — mirrored exactly
  in `RoomBeds`. The exhibit form's type list matches: Double / Twin / Twin-Double
  / Single / Bunk / Sofa Bed. **No information gap on type** — leave `RoomBeds` as
  is (the `property-rooms.md` note about a child `Bed{type,count}` model is a
  nice-to-have, not required for parity; KISS says don't churn it now).

## Proposed model (opinionated)

Bed **size** is a property of a *double* bed (King / Super-king / Emperor); it
does not vary per twin/single. The lowest-churn, no-new-table option that keeps
parity:

```python
class BedSize(models.TextChoices):
    STANDARD    = "standard",    "Standard / not specified"
    KING        = "king",        "King"
    SUPER_KING  = "super_king",  "Super-king"
    EMPEROR     = "emperor",     "Emperor"

# on RoomBeds:
double_size = CharField(choices=BedSize, blank=True)   # applies to the `double` count; "" = unspecified
```

**Design calls:**
- **Size on the double count only**, not a per-bed table. The data only ever
  qualifies doubles (King/Super-king); twins/singles/bunks are unqualified.
  A full `Bed{type,size,count}` child table is more correct but is a bigger
  migration for a fact that only meaningfully attaches to doubles — KISS.
- **`blank` = unspecified**, mapping to the exhibit form's default "0"/empty.
- If the owner later wants zip-and-link (twin↔super-king) or multiple sizes per
  room, that is the trigger to graduate to a child `Bed` model — note it, don't
  build it now.

## Legacy translation (no information loss)

- `RoomBeds` counts migrate **unchanged** (already do) — full type parity, 0 loss.
- `double_size` defaults to `""` on cutover.
- **Best-effort backfill (positives only):** the same preserved placement/description
  text from GAP-065 is scanned for `super\s*king` → `SUPER_KING`, `emperor` →
  `EMPEROR`, `\bking\b` → `KING`. Source text is retained (GAP-065's
  `placement_note`), so a miss loses nothing. Gated behind the GAP-065 backfill
  flag + a reconcile count.

## Frontend

- `RoomFormDialog.tsx`: a `double_size` select shown only when `double > 0`
  (progressive disclosure — don't ask for a king size on a twin room).

## Owner steer

1. **Is bed size customer-facing or internal?** (Drives whether it renders on the
   public site per A3, and whether `STANDARD` should read "Double" vs "King".)
2. **Which sizes are real?** Confirm the ladder — King / Super-king / Emperor
   covers the dump; add "Zip & link" if they split-configure twins.

## Next steps

1. Owner steer 1–2; record in `10-decisions.md`.
2. Add `BedSize` enum + `RoomBeds.double_size`; migration.
3. Serializer + form (conditional on `double > 0`).
4. Fold `super king / emperor / king` into the GAP-065 backfill pass + reconcile row.

## Acceptance

- Bed **counts** unchanged (parity preserved).
- `RoomBeds.double_size` present, optional; form shows it only when `double > 0`.
- Backfill sets sizes from preserved legacy text (positives only); raw text retained.
</content>
