> **✅ RESOLVED (2026-06-19)** — Problem: How should villa cancellation
> policies be stored? Decided: **named policy templates (Strict / Moderate /
> Flexible) selectable per villa, with optional per-villa override** — adds a
> `CancellationPolicy` model wired into the Refund execution path with an
> explicit threshold lookup. (Per-villa-only custom values rejected: no reuse.)
>
> _Original ticket preserved below for context._

# Q-001 — Cancellation policy thresholds

- **Severity:** Question (blocks implementation slice)
- **Source:** `product-design/06-verification.md` open question 1
- **Blocks:** Workflow 16 (cancellation with refund), refund policy
  service layer, `payments/services/refund.py` policy hooks

## Question

Flow 16 references "deposit forfeit < N days from arrival, 50% / 25% /
0% sliding scale on balance". The original system had policies per villa.

Should the new system store cancellation policies as:

- **Named policy templates** (Strict / Moderate / Flexible) selectable
  per villa, with optional per-villa override? **(Design recommendation.)**
- **Per-villa custom values** — every villa carries its own thresholds,
  no shared templates?

## Decision needed

User to confirm: named templates with per-villa override, OR another
shape?

## Follow-up once answered

- Add `CancellationPolicy` model (per recommendation) or per-villa
  fields (alternative).
- Wire into `Refund` execution path with explicit threshold lookup.
- Document the chosen shape in `09-departures.md` and the relevant
  workflow.
