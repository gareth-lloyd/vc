# Q-015 — Owner financial visibility defaults

- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 15
- **Blocks:** Owner portal screens (workflow 14), owner-property
  permission model

## Question

Workflow 14 references `view_full_money` and `view_guest_details`
permissions per owner-property mapping. Confirm:

- Defaults for **new** owner-property mappings — visible by default,
  or hidden by default with explicit opt-in?
- Per-owner override vs per-property override?

## Follow-up once answered

- `OwnerPropertyMapping` model fields and defaults.
- Owner portal screens conditional rendering.
- Test fixtures with both shapes.
