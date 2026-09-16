# Q-010 — Guest data retention / GDPR

> **✅ SUPERSEDED (2026-09-16) — merged into [GAP-095](../gap-095-erasure-propagation-to-zoho.md)** as
> §"Merged from Q-010". Q-010 asks *when* guest data is anonymised, GAP-095 asks *how* that reaches the CRM, and GAP-095 already recorded that neither is answerable alone. Nothing was decided or built by the
> merge; the open work continues there.
>
> _Original ticket preserved below for context._

- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 10
- **Blocks:** `POST /guests/{id}:anonymize` endpoint, retention sweeper

## Question

`04-rest-api-surface.md` §2.17 lists `POST /guests/{id}:anonymize`.
Confirm retention policy:

- Default keep-forever, anonymise on request?
- Auto-anonymise N years after last booking? (If so, what N — 3? 5?
  7?)

## Follow-up once answered

- Anonymise service (already designed via `Contact.merge` pattern).
- Sweeper Celery beat if auto-anonymise is in scope.
- Document in `01-accounts.md`.
