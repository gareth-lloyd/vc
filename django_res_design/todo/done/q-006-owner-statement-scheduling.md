> **✅ RESOLVED (2026-06-22)** — Problem: Flow 18 references "Run this monthly"
> but the owner-statement cadence + delivery channel were unconfirmed, blocking
> the statement generator. Decided: **monthly is the canonical statement period,
> with on-demand generation for any custom range** (the shared reports engine
> already gives this); **delivery is portal-only** — owners download **PDF + CSV**
> from the owner-portal Statements tab (flow 14); **no emailed statements in v1**
> (drops the email-template follow-up below); **operator-triggered generation in
> v1, scheduled auto-send ("Run this monthly" cron + saved-reports panel)
> deferred to v2** (no `django_celery_beat` dependency now; sidesteps the
> over-emailing risk the design repeatedly flags). The implementation (statement
> generator service + read-only portal Statements screen) is now
> decision-unblocked but **blocked on the finance model** — the statement body
> needs commission / deductions / net-payout / payout-status, which belongs to
> the deferred finance rewrite (cf. BUG-009 + the PropertyFinance stub). Track
> the build under Workflow 18.
>
> _Original ticket preserved below for context._

# Q-006 — Owner statement scheduling

- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 6
- **Blocks:** Workflow 18, owner-statement generator + delivery

## Question

Flow 18 references "Run this monthly". Confirm:

- Cadence — **monthly** / **quarterly** / **on-demand only**?
- Delivery channel — **email PDF attachment** / **portal-only** /
  **both**?

## Follow-up once answered

- Statement generator service + Celery beat schedule.
- Owner portal screen update.
- Email template if delivery includes email.
