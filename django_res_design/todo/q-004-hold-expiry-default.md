# Q-004 — Hold expiry default

- **Status:** ✅ **RESOLVED (shape)** (2026-05-27 critique) —
  `10-decisions.md` commits "Hold duration is per-villa default +
  per-hold override" via `PropertySettings.hold_duration_hours`
  inheriting from `GroupSettings`. Numeric default value (48h vs other)
  is still TBD but is a one-line decision.
- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 4
- **Blocks:** `BookingHold` defaults, the hold-sweeper task interval

## Question

Flow 10 uses **48h** as the default hold expiry. Confirm:

- Is 48h the right default?
- Is per-site override needed (or per-property / per-rate-card)?

## Follow-up once answered

- Set the default in `BookingHold.expires_at` computation.
- If per-site needed, add a `hold_expiry_hours` field to `Site` settings.
