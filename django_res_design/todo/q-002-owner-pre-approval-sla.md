# Q-002 — Owner pre-approval SLA

- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 2
- **Blocks:** Workflow 15 (owner approval cycle), the
  PENDING_OWNER_APPROVAL Celery escalation

## Question

Flow 15 references "if owner doesn't respond within site-configured
window, escalation / optional auto-approval". Need:

- Default window — 24h? 48h? 72h?
- Is **auto-approval on timeout** acceptable to the business, or
  must timeouts always escalate to a human?

## Follow-up once answered

- Add the configurable window to `Site` (or `Group`) settings.
- Implement the escalation Celery task in `reservations/tasks.py`.
- Document in workflow 15.
