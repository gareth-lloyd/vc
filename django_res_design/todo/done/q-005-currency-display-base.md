> **✅ RESOLVED (2026-06-19)** — Problem: What base currency + FX source should
> reports normalise to? Decided: **EUR base currency; daily FX snapshot** into
> `pricing.FxRate` `(date, from_currency, to_currency, rate)` via a Celery beat
> job (real-time API rejected — non-deterministic + runtime dependency). Reports
> read the snapshot, not live lookups.
>
> _Original ticket preserved below for context._

# Q-005 — Currency display normalisation in reports

- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 5
- **Blocks:** Reports screens in `02-frontend-design.md` §3.15, the
  FX-conversion service

## Question

Reports normalise to a chosen base currency for charts. Confirm:

- Base currency — **GBP**? **EUR**? **per-site**?
- FX source — real-time API? Daily snapshot from a fixed provider?

## Follow-up once answered

- Add the FX-snapshot model (probably `pricing.FxRate`) with
  `(date, from_currency, to_currency, rate)` and a daily Celery job
  that pulls from the chosen provider.
- Use the snapshot in reports rather than real-time lookups.
