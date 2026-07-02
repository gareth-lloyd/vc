> **✅ RESOLVED (2026-07-02)** — Problem: the TOTP mechanism was built but the
> two policy questions (who is forced to enrol; does refund execution need a
> fresh step-up) were unanswered. Fix: **decided + converted to a build
> ticket.** (1) Enforcement scope = **all staff** (`is_staff=True`) — uniform
> rule over a goes-stale "touches refunds" predicate; non-staff principals
> (owner portal / magic link, both 501 stubs) out of scope. (2) Refund
> execution = **always a fresh TOTP** (single-use, TOTP-window freshness — no
> session step-up cache); approve/reject/cancel do not step up. Decision row
> in `10-decisions.md`; the implementation plan (enforcement middleware +
> `TFA_ENFORCED` flag, single-use `verify_code` replay guard,
> `RefundService.execute` step-up + typed errors, FE forced-enrolment page +
> execute dialog, docs) is **GAP-057**
> (`gap-057-2fa-enforcement-and-refund-stepup.md`). No code change on this
> ticket.
>
> _Original ticket preserved below for context._

> **♻️ RE-SCOPED (2026-06-20, per `CRITIQUE-2026-06-19.md`)** — The TOTP
> *mechanism* is already built: `accounts/services/two_factor.py`
> (enroll/challenge/verify/disable, pyotp, hashed recovery codes) + endpoints
> `auth/2fa:{challenge,verify,enroll,disable}` and admin `users/{pk}:reset-2fa`
> (`accounts/urls.py:39-79`). So "implement a 2FA-required decorator" is no longer
> the work. The two genuinely-open questions below stand: **(1) enforcement
> policy** — which users are *forced* to enrol (admins only / refund-touchers /
> all staff)? — and **(2) refund step-up** — does refund execution require a
> *fresh* TOTP even with 2FA already in session? (No step-up in `payments/` today.)
>
> _Original ticket preserved below for context._

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
