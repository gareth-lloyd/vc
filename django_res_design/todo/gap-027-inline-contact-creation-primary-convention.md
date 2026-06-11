# GAP-027 — Inline contact creation from the property + per-role primary convention

- **Severity:** Gap (UX quick win + decision to record)
- **Source:** 2026-06-11 new-villa setup transcript review
- **Files:**
  `frontend/src/features/properties/components/AssignmentFormDialog.tsx`,
  `frontend/src/features/contacts/` (`ContactPicker`, `onCreateNew`),
  `properties/models/contacts.py` (`PropertyContactAssignment`,
  `one_primary_per_role` constraint)

## Problem

In legacy the loader cannot add a contact from the property: she leaves
the villa, creates the contact in global Contacts (with a forced "NA"
company), assigns the villa, saves, re-opens to set the Owner role
(a legacy bug loses it on first save), then returns to the property to
verify. The new system already fixes the role bug (role is part of the
assignment) and makes company optional — but **inline creation is still
missing**: `ContactPicker` exposes an `onCreateNew` callback that is not
wired in `AssignmentFormDialog`, so the leave-and-return dance survives.

Separately, the transcript surfaced that "primary contact" is
**per-purpose, not per-villa**: her primary is the owner (commercial),
while the concierge team's primary is the house/villa manager
(operational, for client stays). The schema already supports this — the
`one_primary_per_role` constraint allows a primary owner *and* a primary
manager to coexist.

## Proposed fix

1. Wire `onCreateNew` in `AssignmentFormDialog`: create a minimal contact
   (name + email/phone) in a nested dialog and select it into the
   assignment without leaving the property.
2. **Record the convention** (in `10-decisions.md` and the contacts spec):
   there is no single property-wide primary contact. Consumers resolve by
   purpose — commercial/sales → primary OWNER; operations/concierge →
   primary MANAGER (falling back to HOUSEKEEPER); finance → primary OWNER
   unless an OWNERS_REPRESENTATIVE is primary. Do not add a global
   `is_primary` at the property level.

## Acceptance

- A contact can be created and assigned with a role in one flow from the
  People tab.
- Convention recorded; any existing "primary contact" display in the UI
  labels which role it is showing.

## Dependencies

None. Closes out the transcript's contact pain points (role-save bug and
mandatory company are already fixed by construction).
