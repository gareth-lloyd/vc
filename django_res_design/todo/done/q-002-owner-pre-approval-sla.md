> **✅ RESOLVED (2026-06-19)** — Problem: What happens when an owner doesn't
> respond to a booking pre-approval in time, and what's the default window?
> Decided: **timeouts always escalate to a human — no auto-approval on
> timeout** (auto-booking without explicit owner consent rejected as a business
> risk); **default window 24h**, configurable per Site/Group. The 24h escalate
> task already exists; remaining build = make the window configurable.
>
> _Original ticket preserved below for context._

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
