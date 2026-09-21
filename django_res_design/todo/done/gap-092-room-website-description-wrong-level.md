# GAP-092 — Website room copy sits on the room; legacy puts one blurb under all the bedrooms

> **✅ SUPERSEDED (2026-09-16) — merged into [GAP-090](gap-090-description-block-set-parity.md)** as
> §"Merged from GAP-092". Both come from the same Nick recording, both move website description copy to the legacy property-level blocks, and GAP-092's blurb rides GAP-090's enum migration; Q-026 already asked for them to be settled together. Nothing was decided or built by the
> merge; the open work continues there.
>
> _Original ticket preserved below for context._

- **Severity:** 🟢 Gap (customer-facing parity). Backend + frontend +
  data-migration. Small, but carries a data-loss trap.
- **Source:** 2026-07-20 Nick screen-recording (`Recording-20260720_134424`,
  reviewed 2026-08-11). Transcript `[05:21–06:00]`; room dialog captured at
  `[04:55]` / `[05:55]`.
- **Files touched (best-guess):**
  - `django_res/properties/models/rooms.py:35` — `Room.website_description`
    (the field to retire). `vc_notes` (L36) stays.
  - `django_res/properties/serializers/room.py:82`.
  - `django_res/data_migration/loaders/property_children.py:54` — maps legacy
    per-room `WebsiteDescription` onto the room.
  - `django_res/data_migration/loaders/properties.py` `_write_descriptions` —
    property-level legacy `RoomDescription`. *Since GAP-091 (2026-09-09) it
    loads to its own `DescriptionSection.ROOMS` row* (API
    `/properties/{id}/descriptions/rooms`); step 1 below is done, no UI yet.
  - `django_res/data_migration/management/commands/backfill_room_attrs.py:121,128`
    — **reads `website_description` as a keyword source** (see trap below).
  - `frontend/src/features/properties/components/RoomFormDialog.tsx:76, 90,
    465–470` — the Add/Edit room dialog field itself (`Website description`
    sits above `Internal notes`); `tabs/RoomsTab.tsx` only mounts the dialog.
  - `frontend/src/features/properties/schemas.ts:240` (read) and `:361`
    (write form) — note the comment at `:356`/`:368`: `website_description`
    is deliberately `z.string()` rather than nullable, part of the GAP-024
    clearing-trap convention. Removing the field must not disturb `vc_notes`,
    which shares it.
  - `frontend/src/i18n/locales/{en,el}/properties.json:616` —
    `rooms.dialog.fields.website_description` (**both** locales; Greek is
    translated, so don't drop only the English key).

## Problem

Our Add-room dialog has a per-room **Website description** field. The website
doesn't work that way. Nick `[05:38]`: *"underneath the bedrooms we have a
generic text box which refers to all the different rooms. That's just how it's
been designed, so I think we should keep it like that."* And explicitly
`[05:51]`: *"the website description shouldn't be at a room level, it should
be relating to all the rooms."*

He is **endorsing** the legacy design here, not asking for a new feature — the
ask is to stop offering a per-room field that has no home on the public site.

`Room.vc_notes` (internal notes) is fine and stays — `[06:04]`: *"we can keep
internal notes, no problem."*

## Proposed fix

1. **Add a property-level rooms blurb.** The data almost certainly already
   exists: legacy `RoomDescription` is a **property-level** column that the
   loader currently concatenates into `VILLA_INFO`
   (`loaders/properties.py:237–241`). That is very likely this exact box.
   Confirm against the snapshot, then give it its own home — a
   `DescriptionSection` member (`rooms`) is the cheapest, rendering under the
   bedrooms. **Done by GAP-091 (2026-09-09):** `DescriptionSection.ROOMS`
   exists and the loader writes `RoomDescription` into it (a DB loaded before
   then needs the CUTOVER §6e re-run). What remains here is rendering it and
   retiring the per-room field.
2. **Retire `Room.website_description`** from the room dialog and the room
   serializer.
3. ⚠️ **Do not drop the column blind — two traps:**
   - **`backfill_room_attrs` mines it.** The command keyword-scans
     `website_description` + `placement_note` to derive room attribute facets
     (GAP-064). Deleting the field breaks a backfill that is still the only
     source for those facets on imported rooms. Either keep the column as
     import-only (unexposed), or re-run the backfill and retire it after.
   - **Legacy *does* have a per-room `WebsiteDescription` column**
     (`property_children.py:54` maps it), which contradicts "there is no
     room-level description". Most likely the legacy DB carries a column its
     UI doesn't expose — but **verify what's actually in those rows before
     discarding them**, and surface the disagreement rather than silently
     picking a side.

## Acceptance

- A single property-level rooms description exists, editable, rendering under
  the bedrooms. (test)
- The room dialog no longer offers a website description; internal notes
  unaffected. (component test)
- Room attribute backfill still works (or has been re-run and the dependency
  removed) — no facet regression. (test)
- Any legacy per-room `WebsiteDescription` content is accounted for: migrated,
  or documented as an expected loss in `CUTOVER.md`.
- Quality gate green (backend + frontend).

## Dependencies

- **GAP-091** — takes `FeatureDescription`, the other half of the
  `VILLA_INFO` concatenation this ticket splits.
- **GAP-090** — if the blurb becomes a `DescriptionSection` member, it rides
  the same enum migration; sequence together.
- **GAP-064** — room attributes; owns `backfill_room_attrs`, the blocker on
  dropping the column.
