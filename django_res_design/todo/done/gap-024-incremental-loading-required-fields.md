> **✅ RESOLVED (2026-06-18)** — Relaxed `propertyRoomWriteInputSchema.beds`
> from required to optional in `frontend/src/features/properties/schemas.ts`,
> matching the serializer (`RoomSerializer.beds` is `required=False`,
> `room.py:29`) so a room can be saved with just a name. `website_description`/
> `vc_notes` were deliberately left as `z.string().trim()` (a PATCH sends `""`
> to clear them; `.optional()` would emit `undefined` and silently stop
> clearing) — covered by a regression-guard test. The broader structured
> room-attribute posture (ensuite type, aircon, views, accessibility, floor)
> needs an owner vocabulary decision and stays open under **Q-019**; only the
> safe `beds` relaxation shipped here.
>
> _Original ticket preserved below for context._

# GAP-024 — Required-field posture fights incremental property loading

- **Severity:** Gap (workflow regression)
- **Source:** 2026-06-11 new-villa setup transcript review
- **Files:** `frontend/src/features/properties/schemas.ts`
  (`propertyRoomWriteInputSchema`, `propertyCapacityWriteInputSchema`),
  `frontend/src/features/properties/components/RoomFormDialog.tsx`

## Problem

The loader's reality: a new villa arrives with almost no information (in
the transcript she had *only* the room layout) and is filled in over weeks.
In legacy she satisfies required fields by inventing data — "NA" company,
"TBC" surname, made-up addresses and prices — which pollutes the DB and
relies on memory to fix later.

The new backend mostly got this right (nullable OneToOne children,
group-inheritance defaults, all-optional finance). The original premise of
this gap — that the **frontend Zod schemas re-impose strictness**, e.g. the
room form "requires every field including `website_description` and
`vc_notes`" — is **refuted on inspection**: in `schemas.ts` those text
fields are `z.string().trim()` with **no `.min(1)`**, so an empty value
already validates today. The FE text fields are *not* over-strict.

The one field genuinely stricter than the backend is **`beds`**: it is
required in the Zod room write schema, whereas the serializer declares it
`required=False` (`room.py:29`). So the actual incremental-loading friction
narrows to (a) confirming the specific failing write reported in the
transcript, and (b) this `beds` divergence — not a blanket
type-junk-to-save problem across the room form.

## Proposed fix

- **First, confirm the actual reported failing write** from the transcript
  before changing anything. The 2026-06-11 email confirmed the desire to
  "save sections with just the available data rather than using
  placeholders", so reproduce the specific save that failed and verify what
  the schema actually rejects.
- If the goal is incremental room creation, **relax `beds` to optional in
  the room write schema** (+ test) to match the serializer's
  `required=False`.
- **WARNING — do NOT make `website_description`/`vc_notes` `.optional()`.**
  Today edit-mode PATCH sends `""` to clear a value (the model fields are
  `blank=True`); making them `.optional()` would emit `undefined`, omit them
  from the PATCH, and silently stop clearing the field. Keep the `""`
  defaults.
- Leave capacity/finance/settings/descriptions alone — they already match
  the backend posture. Avoid needless churn.
- Prefer explicit emptiness over placeholder text everywhere: optional
  fields render as "not set", and lists/detail views tolerate missing data.

## Acceptance

- A room can be saved with just a name; capacity can be partially saved.
- No FE write schema is stricter than its backend serializer without a
  documented reason.
- Existing edit flows and tests still pass; vitest cover for the relaxed
  schemas.

## Dependencies

Complements GAP-023 (a property stays DRAFT/unapproved while incomplete, so
loose validation is safe).

Must be decided **jointly with Q-019**: structured room attributes touch the
same `Room` model and `RoomFormDialog`, so the incremental-loading posture
should be set once across both tickets rather than twice.
