# Q-010 — Guest data retention / GDPR

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
