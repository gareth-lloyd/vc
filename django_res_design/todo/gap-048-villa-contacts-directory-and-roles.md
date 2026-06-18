# GAP-048 — Villa Contacts directory + role taxonomy

- **Severity:** Gap (data-model + frontend) — after GAP-045
- **Source:** 2026-06-17 owner Contacts-feature review transcript; mockup
  `mock_up_analysis/01-new-res-system.md` §2.14;
  `workflows/05-directory/contact-roles.md`.
- **Files:**
  - `django_res/accounts/enums.py` (`ContactRole`),
    `django_res/properties/models/contacts.py` (`PropertyContactAssignment`)
  - `data_migration/loaders/` (role mapping), FE role dropdowns
  - `frontend/src/features/contacts/` (list columns + detail)

## Problem

(a) The `PropertyContactAssignment` role taxonomy **diverges** from the
owner's / legacy / mockup §2.14 set (Owner / Agent / Villa Admin / Villa
Manager / Management Company). The built enum is
`OWNER / MANAGER / AGENT / HOUSEKEEPER / OWNERS_REPRESENTATIVE`
(`accounts/enums.py:40-46`) — it **adds** housekeeper / owners_rep and is
**missing** `villa_admin` and `management_company`. Note `01-accounts.md:117`
itself calls the enum the "direct replacement" for the legacy 5, yet it doesn't
match them.

(b) The role/category is **not surfaced** in the Villa-Contacts list (columns
are Name | Company | email | phone | status — no role column) or prominently in
the detail.

## Proposed fix

- **Reconcile the role enum.** **Open question in-ticket:** was the divergence a
  deliberate modernization or drift? Re-introduce `villa_admin` /
  `management_company`; decide whether to keep `housekeeper` / `owners_rep`
  (plausible additions the owner didn't ask to remove) — **surface the mismatch,
  don't assume deletion.** Touches `accounts/enums.py`,
  `properties/models/contacts.py`, loaders, FE dropdowns.
- **Allow `Organisation` assignees** — a `management_company` role should be
  able to reference an `Organisation` (GAP-046), not only a `Person`.
- **Surface the role** in the Villa-Contacts list (chip/column) and detail.
- **Address: dropped — subsumed by GAP-045** (Person already carries the rich
  `town/post_code/country` address). The owner's "missing address fields" is
  satisfied there; only verify the Villa-Contacts detail *renders* it.

**Caveat 1 (from the UI assessment):** keep the **Villa-Contacts form distinct
from the Clients form** over the shared `Person` identity — roles / linked
properties / groups here, vs tags / relationships / history on the Clients side
(mockup §2.14 vs §2.12).

## Acceptance

- Role enum covers the owner's taxonomy (Owner / Agent / Villa Admin / Villa
  Manager / Management Company); the keep/drop call on housekeeper/owners_rep is
  recorded.
- `management_company` assignments can point at an `Organisation`.
- Villa-Contacts list/detail shows the role and the (Person) address.

## Dependencies

Depends on **GAP-045** (Person) and **GAP-046** (Organisation assignees).
Relates to `workflows/05-directory/contact-roles.md` (its open role/group
table-split question).
