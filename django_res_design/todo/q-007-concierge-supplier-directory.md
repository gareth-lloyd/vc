# Q-007 — Concierge supplier directory shape

- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 7
- **Blocks:** Workflow 9 (concierge), the concierge module's data model

## Question

The design treats concierge suppliers as `Contact` rows (flow 9).
Confirm:

- Does this match the operating model — suppliers really are just
  contacts with a tag?
- Or do suppliers need their own entity with contracts, payment terms,
  insurance docs, etc.?

## Follow-up once answered

- If contact-only: stop here, document.
- If standalone entity: add `Supplier` model + relationship to
  `ConciergeItem`.
