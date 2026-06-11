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
group-inheritance defaults, all-optional finance). But the **frontend Zod
schemas re-impose strictness**: the room form requires every field
including `website_description` and `vc_notes`; capacity requires all
counts. That recreates the type-junk-to-save problem for the exact
sections she fills incrementally.

## Proposed fix

- Audit the property write schemas in `schemas.ts` against the backend's
  `blank=True`/`null=True` posture and relax FE-only requirements: for
  rooms, require `name` only (placement defaults, descriptions/notes
  optional, bed counts default 0); for capacity keep the fields but allow
  partial save (the guests==0 hidden-from-quotes warning already exists —
  warnings over walls).
- Prefer explicit emptiness over placeholder text everywhere: optional
  fields render as "not set", and lists/detail views tolerate missing data.
- Sweep the remaining property tabs for the same pattern while in there
  (finance is already all-optional — that's the model to match).

## Acceptance

- A room can be saved with just a name; capacity can be partially saved.
- No FE write schema is stricter than its backend serializer without a
  documented reason.
- Existing edit flows and tests still pass; vitest cover for the relaxed
  schemas.

## Dependencies

None. Complements GAP-023 (a property stays DRAFT/unapproved while
incomplete, so loose validation is safe).
