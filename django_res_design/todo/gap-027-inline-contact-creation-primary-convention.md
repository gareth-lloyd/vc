# GAP-027 — Inline contact creation from the property + per-role primary convention

> ℹ️ **Note (2026-06-18):** under the unified-`Person` model (GAP-045), the
> picker + inline-create flow targets `Person` / `Organisation` rather than
> `Contact`. The per-role-primary convention (`one_primary_per_role`) is
> unaffected. No change to this ticket's substance.

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
assignment) and makes company optional. **Inline creation is also already
in place**: `PeopleTab.tsx` (~548-569) wires the full inline-create flow
using the existing reusable `ContactFormDialog`, so the leave-and-return
dance is gone. Two genuine defects remain, however:

- The newly created contact is **not auto-selected** back into the picker.
  `onCreated` (`PeopleTab.tsx:565-567`) only re-opens the assignment dialog,
  so the user must re-find the contact they just made.
- The per-role-primary convention is enforced in code but **not documented**
  anywhere in the specs.

Separately, the transcript surfaced that "primary contact" is
**per-purpose, not per-villa**: her primary is the owner (commercial),
while the concierge team's primary is the house/villa manager
(operational, for client stays). The schema already supports this — the
`one_primary_per_role` constraint allows a primary owner *and* a primary
manager to coexist.

## Proposed fix

1. **Auto-select the new contact.** Fix `onCreated`
   (`PeopleTab.tsx:565-567`) so that, after the contact is created, it is
   selected into the picker rather than only re-opening the assignment
   dialog. Reuse the existing `ContactFormDialog` — do **not** build a new
   minimal-contact dialog; the inline-create flow already works.
2. **Record the convention** (in `10-decisions.md` and the contacts spec):
   there is no single property-wide primary contact. Consumers resolve by
   purpose — commercial/sales → primary OWNER; operations/concierge →
   primary MANAGER (falling back to HOUSEKEEPER); finance → primary OWNER
   unless an OWNERS_REPRESENTATIVE is primary. Do not add a global
   `is_primary` at the property level. Note the `one_primary_per_role`
   constraint **already exists** in code
   (`properties/models/contacts.py:43-47`), so this is documentation only —
   no new enforcement.

> **Out of scope:** a separate FE/BE required-field divergence — the FE
> allows company-only contacts while the backend `Contact` requires
> `first_name` + `last_name` — is spun out to **gap-029**. Do not solve it
> here. The 2026-06-11 email confirmed both contacts-from-the-villa-page and
> company-not-required are wanted, which informs gap-029's direction toward
> loosening the backend.

## Acceptance

- After a contact is created inline from the People tab, it is
  auto-selected into the picker (no need to re-find it).
- Convention recorded; any existing "primary contact" display in the UI
  labels which role it is showing. No new constraint added —
  `one_primary_per_role` already enforces it.

## Dependencies

None. Closes out the transcript's contact pain points (role-save bug and
mandatory company are already fixed by construction).
