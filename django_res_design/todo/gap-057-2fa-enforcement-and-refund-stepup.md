# GAP-057 — 2FA: staff enrolment enforcement + refund-execution step-up

- **Severity:** Gap (security posture; mechanism built, policy unenforced)
- **Source:** Q-008 (converted 2026-07-02 with the policy decided);
  `product-design/06-verification.md` open question 8
- **Blocks:** production-hardening of the auth surface; the refund money-out path
- **Files:**
  - `accounts/services/two_factor.py` (`TwoFactorService` — enroll / challenge /
    verify / disable, pyotp, hashed recovery codes)
  - `accounts/views/auth.py:58` (`LoginView` already branches enrolled users into
    the challenge flow), `:197` (`TfaEnrollView`), `:271` (`TfaVerifyView`),
    `:295` (`TfaDisableView`)
  - `accounts/urls.py:39-43` (`auth/2fa:*`), `:79` (`users/{pk}:reset-2fa`)
  - `accounts/models/user.py` (`tfa_method` / `tfa_secret` / `tfa_enrolled_at` /
    `tfa_recovery_codes`)
  - `payments/views/refund.py:72` (`execute` action), `payments/services/refund.py:57`
    (`RefundService`)
  - `core/exceptions.py` (typed `DomainError` contract, SMELL-010)
  - `frontend/src/features/auth/` (`LoginPage` → `TfaChallengePage` flow, `api.ts`,
    `store.ts`, `schemas.ts` — challenge/verify shipped; **no enrolment UI exists**)
  - `frontend/src/features/bookings/` refunds UI (`RefundsSection`)
  - `villacollective/settings/{base,dev,test,production}.py`

## Decision (settles Q-008)

Recorded in `10-decisions.md`, 2026-07-02:

1. **Enforcement scope — all staff.** Every `is_staff=True` user must have TOTP
   enrolled to use the API. Not "admins + refund-touchers": the team is small,
   one uniform rule beats maintaining a goes-stale "touches refunds" predicate,
   and `User.role` defaults to `VIEWER` for everyone so role is not a usable
   gate anyway. Non-staff principals (future owner-portal / magic-link logins —
   both currently 501 stubs) are out of scope.
2. **Refund step-up — always fresh.** `POST /refunds/{id}:execute` requires a
   valid, unused TOTP code on every call, even when the session already
   completed a 2FA login. Freshness is the TOTP window itself (±1 step) plus a
   single-use replay guard — no "verified N minutes ago" session cache to
   design, expire, or leak. Approve/reject/cancel do **not** step up (approval
   is already SoD-guarded; execute is the money-out click).

## Problem

The TOTP *mechanism* is complete (service, endpoints, login branch, FE
challenge page) but nothing *forces* enrolment — a staff user who never visits
`:enroll` authenticates with password only, forever. And `:execute` on a refund
is a plain session-authenticated POST: a hijacked cookie is sufficient to move
money out. The design intent ("admin-forced for users touching refunds") was
never mechanised.

## Plan

Six units, each a small test-backed commit; backend first. Units 1–3 are
independent of 4–5 (FE) except for the error-code contract, which Unit 2/3 fix
first.

### Unit 1 — single-use TOTP verification helper (backend)

- Add `User.tfa_last_verified_step = BigIntegerField(null=True)` (migration;
  no backfill needed).
- Add `TwoFactorService.verify_code(user, code) -> bool`: pyotp verify with
  `valid_window=1`, then reject-and-record on the timestep — a code that
  matches `tfa_last_verified_step` (or older) is refused, a fresh one stores
  its step inside the same row update. This is the replay guard the login
  path currently lacks and the step-up path must have.
- Refactor the TOTP branch of `TwoFactorService.verify()` (login challenge)
  onto the helper so login and step-up share one verification path; the
  recovery-code fallback **stays login-only** (recovery codes are a lockout
  escape hatch, not a money-movement credential).
- Tests: fresh code accepted once, replayed code rejected, window-edge codes,
  recovery path untouched.

### Unit 2 — enrolment-enforcement middleware (backend)

- `accounts/middleware.py::TfaEnforcementMiddleware`, installed after
  `AuthenticationMiddleware`. Predicate: `settings.TFA_ENFORCED` **and**
  `request.user.is_authenticated` **and** `user.is_staff` **and**
  `user.tfa_method == NONE` **and** path not in the allowlist → 403 JSON
  `{"code": "tfa_enrollment_required", "detail": …, "field_errors": {}}`
  (matches the canonical error envelope).
- Allowlist (exact, tested): `auth/csrf`, `auth/login`, `auth/logout`,
  `auth/me` (FE boot probe), `auth/permissions`, `auth/2fa:enroll` — the
  minimum for a logged-in-but-unenrolled user to complete enrolment and
  nothing else. (`auth/2fa:verify` is `AllowAny` pre-session; unaffected.)
- Guard `TfaDisableView`: when the predicate would re-trip (enforced + staff),
  `:disable` returns the same 403 — self-serve disable would be an enforcement
  bypass. Admin `users/{pk}:reset-2fa` stays the escape hatch (lost phone →
  reset → user funnels back into forced enrolment on next request).
- Settings: `TFA_ENFORCED = False` in `base` (so dev/test/seed_dev stay
  ceremony-free), `True` in `production` (staging inherits). Targeted tests
  use `override_settings(TFA_ENFORCED=True)` — the suite at large never
  notices.
- Tests: unenrolled staff blocked on an arbitrary endpoint / allowed on every
  allowlist entry; enrolled staff unaffected; non-staff user unaffected; flag
  off ⇒ no-op; `:disable` blocked when enforced.

### Unit 3 — refund-execution step-up (backend)

- New typed error in `core/exceptions.py`: `TfaStepUpRequired(DomainError)`,
  `code = "tfa_stepup_required"`, `status_code = 403` — distinct from
  `forbidden` so the FE can render a code prompt rather than a permissions
  wall. Invalid/replayed codes raise `DomainValidationError` subclass
  `InvalidTfaCode` (`code = "invalid_tfa_code"`, 400) so retry-with-new-code
  is distinguishable from not-allowed.
- `RefundService.execute(refund, actor, totp_code: str | None = None)`:
  after the existing permission check, when `actor` is a real user (the
  documented `actor=None` system sentinel is exempt) — missing code ⇒
  `TfaStepUpRequired`; `TwoFactorService.verify_code` failure ⇒
  `InvalidTfaCode`. Service-layer placement follows the house rule
  (perms live in services, not views); `payments → accounts` is a clean
  downward spine import.
- Actor not enrolled at all ⇒ `TfaStepUpRequired` with an "enrol first"
  detail (only reachable while `TFA_ENFORCED` is off — belt and braces).
- View passes `request.data.get("tfa_code")` through; no serializer change
  beyond the optional field. Structured log event on success
  (`refund.stepup_verified`, refund_id + user_id — never the code).
- Tests: system caller exempt; missing / invalid / replayed / stale code;
  happy path executes exactly as before with a valid code; error codes
  surface through the canonical exception handler.

### Unit 4 — forced-enrolment UX (frontend)

- Query/HTTP layer: on any `403 tfa_enrollment_required`, route to a new
  `/enroll-2fa` page (pattern-match the existing 401→login redirect in the
  auth store/interceptor).
- `Enroll2faPage`: calls `POST auth/2fa:enroll` (no code) → renders the
  `provisioning_uri` as a QR (off-the-shelf `qrcode.react`; show the base32
  secret as copyable fallback) → 6-digit confirm submit (`:enroll` with code)
  → one-time recovery-codes screen with an explicit "I've saved these"
  acknowledgement before continuing into the app.
- Zod schemas for both `:enroll` response shapes; en+el i18n; vitest for the
  three-step flow + the interceptor redirect (msw).

### Unit 5 — refund step-up dialog (frontend)

- Refunds execute action opens a small dialog: 6-digit code input, submit
  posts `{tfa_code}` to `:execute`. `invalid_tfa_code` renders inline retry;
  `tfa_stepup_required` (e.g. dialog bypassed) reopens it. en+el; vitest on
  the dialog + error mapping.

### Unit 6 — docs + ticket hygiene

- `01-accounts.md`: enforcement policy, middleware contract, allowlist,
  `TFA_ENFORCED` flag, disable-guard; `07-payments.md`: `:execute` step-up
  contract (`tfa_code`, both error codes). `04-rest-api-surface.md` if the
  endpoint tables list request bodies.
- `10-decisions.md`: the two-part decision row (scope + always-fresh step-up).
- INDEX row flips.

## Rollout note (production)

Flipping `TFA_ENFORCED=True` in production funnels **every existing staff
user** into the enrolment screen on their next request — by design, but
announce it (they need their phones), and confirm Render env/settings before
the deploy per the local-main push checklist. seed_dev/dev/test are
unaffected (flag off). No data migration beyond the nullable
`tfa_last_verified_step` column.

## Acceptance

- With `TFA_ENFORCED=True`: an unenrolled staff session can reach exactly the
  allowlist and nothing else; completing enrolment unblocks without re-login.
- `:disable` refused while enforcement applies; admin `:reset-2fa` +
  re-enrolment round-trip works.
- `:execute` without / with invalid / with replayed code fails with the
  documented codes; with a fresh code it executes; the same code twice fails
  the second time. System (`actor=None`) refund execution unaffected.
- FE: forced-enrolment flow (QR → confirm → recovery ack) and the execute
  step-up dialog, both i18n'd (en+el) and vitest-covered.
- Suite green with the flag off globally; enforcement tests opt in via
  `override_settings`.

## Dependencies

- Built on the shipped TOTP mechanism (see Q-008 re-scope banner, 2026-06-20).
- `RefundService` SoD rules (BUG-010) untouched — step-up is additive after
  the existing permission check.
- Future owner-portal / magic-link logins (both 501 today) are explicitly
  outside the enforcement predicate (`is_staff` gate).
