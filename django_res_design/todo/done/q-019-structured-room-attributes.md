# Q-019 — Structured room attributes (bath/shower, aircon, views, accessibility, floor)

> **✅ SUPERSEDED (2026-07-02)** by three legacy-grounded build tickets:
> [GAP-064](../gap-064-structured-room-attributes.md) (room attributes —
> enum-column facets + an admin-editable `RoomAttribute` catalog),
> [GAP-065](../gap-065-room-location-building-floor.md) (building + floor; also
> fixes a live migration data-loss bug where `RoomLoader` discards every
> `PlacementId`), and [GAP-066](../gap-066-room-bed-size.md) (bed size). The
> A1/A2 owner-vocabulary decision this ticket raised is carried in those tickets'
> "Owner steer" sections and the
> [owner-questions](../owner-questions-2026-07-02.md) round. No work remains here.

- **Severity:** Question (vocabulary decision) + build
- **Source:** 2026-06-11 new-villa setup transcript review
- **Files:** `properties/models/rooms.py` (`Room`, `RoomBeds`),
  `frontend/src/features/properties/components/RoomFormDialog.tsx`,
  `properties/models/features.py`

## Problem

The loader types room attributes as free text in a memorised fixed order:
bed type, "ensuite shower" (vs bath), air conditioning, then when known —
sea view, balcony, terrace, outside access — plus internal-only notes for
unadvertisable facts (pull-out child beds, shared bathrooms, mosquito
screens). The convention lives in her head; nothing enforces or queries it.

The new model keeps structured bed counts (`RoomBeds`), `is_ensuite`,
`placement`, `vc_notes` — good — but everything else still lands in
free-text `website_description`, recreating the convention. Two concrete
costs from the transcript:

1. **Wheelchair accessibility is triple-entered** — room note, features
   page, description — all from memory ("I'd make sure I put that on the
   features page as well").
2. **Floor/level isn't data** — she encodes "first floor / ground floor /
   lower floor" in text and manually keeps same-floor rooms adjacent in
   the sort order.

## Proposed direction

Add a small structured attribute set to `Room`:
`ensuite_type` (shower/bath/both — refines `is_ensuite`), `has_aircon`,
`has_sea_view`, `has_balcony`, `has_terrace`, `has_outside_access`,
`is_wheelchair_accessible`, `floor` (small enum or signed int; drives
default grouping in the rooms list). Derive/prompt the property-level
accessibility feature from any accessible room instead of relying on
double entry. `website_description` stays for prose; `vc_notes` stays
internal.

This must be decided **jointly with GAP-024** — both touch the same `Room`
model and `RoomFormDialog`, and the incremental-loading required-field
posture (which room fields are optional) should be set once across both.
The 2026-06-11 email ("save sections with just the available data") supports
making these new structured attribute fields all-optional/nullable.

## Open questions (for the loader / product)

1. Is the transcript's list the complete attribute vocabulary, or are
   there more (e.g. interconnecting rooms, ground-floor access)?
2. Floor vocabulary: lower/ground/first/second… enum, or free numbering?
3. Should the website render these as structured icons/list (new
   behaviour) or keep prose only (legacy-faithful, attributes internal)?
   Customer-facing output should follow legacy unless agreed otherwise.

## Acceptance

- Attribute set agreed and recorded; model + migration + room form fields.
- Property accessibility feature derived or prompted from room data.
- Rooms list groups/sorts by floor by default (manual `sort_order` kept).

## Dependencies

- **GAP-024 — decide jointly.** Both tickets touch the same `Room` model and
  `RoomFormDialog`. The incremental-loading required-field posture (which room
  fields are optional/nullable) must be set once across both; the 2026-06-11
  email ("save sections with just the available data") supports making these
  new structured attribute fields all-optional/nullable.
- Q-021 (taxonomy curation) for the property-level feature vocabulary.
