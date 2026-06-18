# GAP-032 — Click-and-drag availability block creation

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
