> **✅ RESOLVED (2026-07-02)** — Problem: do concierge suppliers need their own
> entity (contracts, payment terms, insurance docs) or are they contact rows?
> Fix: **contact-only.** Since the ticket was filed, GAP-045/046/048 delivered a
> unified `Person`, an `Organisation` entity, and a role-scoped Suppliers
> directory — "just a contact" is now a typed person *or company*. The workflow-9
> spec needs only an optional supplier picked from the directory plus per-line
> internal `supplier_cost` (margin), and legacy had no supplier entity at all
> (margin was an operator spreadsheet) — nothing demands contracts/insurance.
> When the concierge module is built, `ConciergeLineItem` gets a nullable
> supplier FK (`Person`/`Organisation`) and `supplier_cost` lives on the line,
> not the supplier. Concierge role vocabulary (chef, transfer company, …),
> the optional `notify_on_concierge_request` flag, and the "Suppliers"
> directory-label collision flagged in GAP-048 are decided **when that module
> is picked up** — they need no model headroom now. Decision row added to
> `10-decisions.md`. No code change.
>
> _Original ticket preserved below for context._

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
