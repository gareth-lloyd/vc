# Q-025 — Room floor: A2 ladder seen and endorsed; settle the unparsed remainder

- **Severity:** Question (owner confirmation + a known reconcile gap).
  **No new build** — GAP-065 already shipped everything Nick asked for.
- **Source:** 2026-07-20 Nick screen-recording (`Recording-20260720_134424`,
  reviewed 2026-08-11), relaying Brian E. Transcript `[04:45–05:10]`; our Add
  room dialog captured at `[04:55]`.
- **Files:**
  - `django_res/data_migration/placement_parsing.py` — `parse_placement`
    (GAP-065), keyword parser over legacy `VillaRoomsPlacement.Name`.
  - `django_res/properties/enums.py:70` — `RoomFloor` (the A2 ladder).
  - `django_res/data_migration/loaders/property_children.py:46–53` — raw
    string preserved verbatim in `Room.placement_note`.
  - `done/gap-065-room-location-building-floor.md` — the shipped build.

## What the recording settles

Brian's note, via Nick `[04:48]`: *"the floor is not a dropdown on our current
res system, it's actually free text… I think a dropdown would be much
better."*

**This already exists.** The Add-room dialog at `[04:55]` shows Floor as a
dropdown — *Not set / Lower ground floor / Ground floor / First floor /
Second floor / Third floor or above* — alongside a separate Placement axis.
That is GAP-065's `RoomFloor` ladder, shipped 2026-07-05 on the **ticket
default A2 vocabulary with owner confirmation pending**. Nick is looking
straight at it and endorsing it, so **treat A2 as confirmed** unless someone
objects — and record that in `design/decisions.md`, where it currently sits
under "Open follow-ups".

## What is still open

Nick `[04:57]`: *"I'm just slightly concerned about how that's going to pull
through from the previous system… I think how it's done is 'Master - First
floor'. So I'm not sure how that's going to pull over, but that's something
perhaps we can talk about."*

The mechanism exists — `parse_placement` word-matches
`\bfirst[\s-]+fl?oor` (the typo `"First foor"` is handled), so
`"Master - First floor"` does parse to `FIRST`, and anything unparsed keeps
its raw string in `placement_note`, so nothing is lost. Two residuals remain:

1. **The 49-row reconcile gap.** GAP-073's live dry-run on the 24-Apr dump
   surfaced a `Room placement (GAP-065)` reconcile gap of **49** rows, listed
   there as a pre-existing follow-up and never chased. That is the concrete
   answer to Nick's question and should be quantified before the
   conversation, not during it.
2. **Ambiguous rungs stay blank by design** — `"upper floor"`, `"upper
   level"`, `"lower level"`, `"mezzanine"`, `"basement"` deliberately parse to
   `""` pending the A2 steer. With Nick on the call this is answerable: do
   these get ladder rungs, or stay unset with the note?

Worth noting the room he types in the video is named **"Master 1"** — legacy
room *names* also carry position information, a second channel the parser
doesn't read.

## Proposed direction

1. Run `parse_placement` over the current snapshot and produce a coverage
   count: parsed to a floor / parsed to a building / left blank, with the top
   unparsed strings by frequency. That's a half-hour query and it turns the
   worry into a number.
2. Take the top unparsed strings to Nick with the two questions above
   (ambiguous rungs; whether room *names* should be a parse source).
3. Extend the patterns or accept the remainder as blank-with-note, then close
   the GAP-073 reconcile row.
4. Record the A2 confirmation in `design/decisions.md`.

## Acceptance

- Parse coverage measured and recorded; the 49-row gap explained or closed.
- Ambiguous-rung decision recorded in `design/decisions.md`.
- A2 ladder marked confirmed (or revised) in `design/decisions.md`.

## Dependencies

- **GAP-065** (resolved) — the build being confirmed here.
- **GAP-073** (resolved) — surfaced the 49-row reconcile gap.
- Related: **GAP-064** A1 room-attribute vocabulary, the sibling pending
  owner confirmation — worth putting to Nick in the same conversation.
