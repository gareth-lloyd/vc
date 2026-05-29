# Q-008 — 2FA enforcement scope

- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 8
- **Blocks:** Auth middleware / login flow, refund-execution path

## Question

Design says 2FA is "admin-forced for users with `is_admin` and any
operator who touches refunds". Confirm:

- Is the rule exactly that, or broader (all staff)?
- Should the refund-execution endpoint **always** require a fresh TOTP
  step-up, even for admins with 2FA already in their session?

## Follow-up once answered

- Implement 2FA-required decorator on the relevant view/service.
- Document in `01-accounts.md` and `07-payments.md`.
