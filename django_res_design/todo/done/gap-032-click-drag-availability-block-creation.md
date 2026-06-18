# GAP-032 — Click-and-drag availability block creation

> ✅ **RESOLVED (2026-06-18).** Press-drag-release on a villa's month grid opens
> the existing create dialog pre-filled with the dragged range (reason/notes
> still chosen in the dialog); typed-range entry and single-cell edit are
> unchanged. New pure `lib/dragRange.ts#resolveDragRange` anchors on the press
> origin and truncates the selection before the first non-selectable day
> (half-open `date_to = lastNight + 1`, matching the picker and backend overlap
> predicates), so a drag can't span an occupied/booked day. The grid uses
> pointer-event delegation (drag starts only on selectable cells; no
> `setPointerCapture`; a `window` `pointerup` commits) so editable-block
> dropdowns and booking links keep working, and drag is role-gated to
> reservations users. `AvailabilityBlockFormDialog` gained an optional
> `initialRange` create prop. Vitest covers the range mapping
> (forward/reverse/single-day/occupied-truncation) and the grid drag →
> pre-filled dialog. FE-only, no API change. Quality gate green.

- **Severity:** Gap (FE UX; reduces friction for busy update windows)
- **Source:** owner Loom walkthrough 2026-06-17 (availability section, 1:20–1:46):
  "the way that we add availability is a little bit clunky… putting the date
  range. We need to make this as easy for people as possible… if we could have
  click and drag, then I like, that would make life much easier."
- **Files:** `frontend/src/features/properties/tabs/AvailabilityTab.tsx`,
  `frontend/src/features/properties/components/AvailabilityBlockFormDialog.tsx`,
  `frontend/src/lib/monthGrid.ts`.

## Problem

Adding availability today means opening a dialog and typing a date range. When
the sales / experience team are busy fielding updates, the typed-range flow is
slow ("a bit of a busy update… this won't be able to chuck it in").

## Proposed fix

Frontend only. Add **click-and-drag range selection directly on the month grid**
in `AvailabilityTab.tsx` (built on `lib/monthGrid.ts`): press on a start day,
drag to an end day, release to open the existing `AvailabilityBlockFormDialog`
pre-filled with the selected range (reason/notes still chosen in the dialog).
Keep the existing typed-range entry and the single-cell click-to-edit as
fallbacks. Respect the same occupied/already-booked greying the dialog already
applies — drag selection can't span days that aren't selectable.

No backend change: the existing `POST /properties/{id}/availability` /
`PATCH /availability/{id}` contract is unchanged.

## Acceptance

- Press-drag-release on the month grid opens the create dialog pre-filled with
  the dragged `date_from`/`date_to`.
- Drag selection cannot cross occupied/booked days (mirrors current dialog rules).
- Typed-range entry and single-cell edit still work.
- Vitest covers the drag-to-range mapping (incl. reverse drag, single-day drag,
  and a drag blocked by an occupied day).

## Dependencies

None (FE-only; no API change).
