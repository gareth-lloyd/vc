# GAP-058 — comms is pull-only: retire all seven blessed comms back-edges

- **Severity:** Gap (architecture contract; the layers rule exists but seven
  blessed exceptions contradict it)
- **Source:** Q-017 (converted 2026-07-02 with the decision recorded); the
  2026-06-10 backend general review
- **Blocks:** nothing hard — but every new email feature re-fights the
  "signal or direct call?" choice until this lands, and the blessed-exception
  list grows each time the direct-call side wins
- **Files:**
  - `pyproject.toml:210-216` (the seven blessed comms-bound `ignore_imports`)
  - `payments/tasks.py:112-398` (`send_payment_reminders` +
    `_send_payment_reminders` / `_send_security_deposit_reminders` /
    `_payment_reminder_band` / `_dispatch_sd_bands` / `_reminder_already_sent` /
    `_dispatch` / `_reminder_context`)
  - `comms/tasks.py` (existing dispatch + `requeue_stuck_emails` beat sweep —
    the reminder sweep's natural home)
  - `villacollective/settings/base.py:302-303` (`send-payment-reminders` beat
    entry)
  - `accounts/services/password_reset.py:17` (direct `EmailService` call),
    `accounts/signals.py` (existing module — new signal lands here)
  - `comms/signals.py` (`_register()` at :469 — receiver registration point)
  - `reservations/urls.py:12,276-286` (`bookings/{pk}/emails` routes importing
    `comms.views.BookingEmailViewSet`), `comms/urls.py`

## Decision (settles Q-017)

Recorded in `10-decisions.md`, 2026-07-02: **comms stays top-of-spine and
becomes strictly pull-only.** Nothing below comms ever imports it. comms
consumes the domain two ways, both already established in the codebase:

1. **Events** — signal receivers in `comms/signals.py`, registered from
   `apps.py::ready()`, listening to domain signals (the existing eight
   handlers: booking transitions, quotation sent, payment succeeded/failed,
   SD released, …).
2. **Time** — beat-scheduled sweeps in `comms/tasks.py` that *read* domain
   models directly (clean downward imports) and dispatch email.

With that rule, the "signal or direct call?" fork disappears structurally:
a direct call from a domain app fails `lint-imports`, so there is nothing to
re-litigate. End state: **zero** blessed comms back-edges in `pyproject.toml`
(the only remaining blessed edge in the whole contract is
`properties.filters.property → reservations.models.booking`).

## Problem

Seven of the eight blessed back-edges in the layers contract point *up* into
comms:

```toml
"accounts.services.password_reset -> comms.services",
"reservations.urls -> comms.views",
"payments.tasks -> comms.enums",
"payments.tasks -> comms.models",
"payments.tasks -> comms.exceptions",
"payments.tasks -> comms.recipients",
"payments.tasks -> comms.services",
```

Each exists because a piece of comms work was built in the wrong place or
wired as a direct call. Inspection shows all seven dissolve without inventing
anything:

- The five `payments.tasks` edges all serve `send_payment_reminders` — a
  **pure notification sweep**. It reads `Payment`/`SecurityDeposit` due
  dates, dedups against `EmailLog` (hence the `comms.models` import), and
  dispatches; it mutates no payment state (the webhook and SD-refund tasks in
  the same module are separate functions and touch no comms code). It is a
  comms job living in `payments/`.
- The `password_reset` edge is a genuine domain **event** expressed as a
  direct call — the only email path not going through `comms/signals.py`.
- The `reservations.urls` edge is **routing only** — reservations imports a
  comms viewset purely to mount `bookings/{pk}/emails`. Django URL confs are
  global; comms can mount that path itself (comms importing reservations is a
  clean downward edge).

## Plan

Three small test-backed commits + a docs close-out. Order is free; each unit
independently prunes its `ignore_imports` lines and must leave
`uv run lint-imports` green.

### Unit 1 — move the reminder sweep into comms (kills 5 edges)

- Move `send_payment_reminders` and its seven helpers from
  `payments/tasks.py` to `comms/tasks.py` (beside `requeue_stuck_emails`,
  which established the "comms beat sweep reads domain rows" pattern). The
  comms imports become local; `payments.models` / `reservations` reads become
  clean downward imports.
- Update the beat entry: `"task": "comms.tasks.send_payment_reminders"`
  (`settings/base.py:302`). Keep the schedule key and cadence; the
  neighbouring comment about the 07:00 ordering moves intact. Deploy note:
  fire-and-forget beat task, so a rename is safe — no in-flight results to
  strand; one beat tick at most is lost if workers roll before beat.
- Move the reminder tests (`payments/tests/` → `comms/tests/`) wholesale;
  they already exercise the sweep through EmailLog assertions.
- Prune the five `payments.tasks -> comms.*` lines.
- `payments/tasks.py` keeps `process_webhook_delivery`,
  `sweep_unprocessed_webhook_deliveries`, `process_sd_refunds` — none touch
  comms.

### Unit 2 — password reset becomes an event (kills 1 edge)

- New `password_reset_requested` signal in `accounts/signals.py`
  (providing kwargs: user, reset token/url — whatever
  `PasswordResetService.request` currently hands to `EmailService`; token
  generation stays in accounts).
- `PasswordResetService.request` fires the signal instead of calling
  `EmailService`; receiver added to `comms/signals.py` + wired in
  `_register()` alongside the existing imports of domain signal modules.
  Receivers run synchronously in the sender's transaction (same semantics as
  today's direct call — `EmailService` already defers actual SMTP to
  on-commit), so the anti-enumeration 204 contract of
  `POST /auth/password-reset:request` is unchanged.
- Use the established `_safe_send` wrapper so a template/profile problem
  can't 500 the reset endpoint (today's direct call *can* — this is a small
  hardening win, note it in the commit).
- Prune `accounts.services.password_reset -> comms.services`.
- Tests: existing password-reset email tests keep passing (moved/rewired as
  needed); a receiver test in comms; a no-receiver smoke (signal fires even
  if comms app were absent — plain `Signal.send`).

### Unit 3 — comms mounts its own booking-email routes (kills 1 edge)

- Move the two `bookings/<int:booking_pk>/emails[...]` paths from
  `reservations/urls.py:276-286` into `comms/urls.py`; drop the
  `comms.views` import from reservations. Path strings, names
  (`booking-emails`, `booking-email-resend`) and URL shapes are unchanged —
  the SPA sees no difference; `reverse()` callers are unaffected by which
  app's conf declares the route.
- Prune `reservations.urls -> comms.views`.
- Tests: existing endpoint tests keep passing untouched (they hit paths, not
  URL confs); add a `reverse()` smoke if one doesn't exist.

### Unit 4 — docs close-out

- `00-conventions.md` + `django_res/CLAUDE.md` layers section: state the
  pull-only rule ("nothing imports comms; comms consumes via signal
  receivers and its own beat sweeps") as the *reason* comms is top-of-spine.
- `10-decisions.md` row (done at conversion — verify it matches what
  shipped). `10-comms.md` if it describes the reminder task's home.
- INDEX flip.

## Acceptance

- `pyproject.toml` contains **zero** `-> comms` lines in `ignore_imports`;
  `uv run lint-imports` passes.
- `send_payment_reminders` runs from `comms.tasks` via the same beat key and
  cadence; reminder + SD-reminder behaviour pinned by the moved tests.
- Password-reset email flows through a `comms/signals.py` receiver; the
  endpoint still returns 204 regardless of address validity; a template
  failure no longer 500s the endpoint.
- `bookings/{pk}/emails` and `:resend` respond exactly as before (same
  paths, same names).
- Full backend suite green.

## Dependencies

- SMELL-015 (transient SMTP retry) already landed in `comms/tasks.py` —
  the moved sweep dispatches through the same path; no interaction.
- FG-013 (owners app in the contract) already landed; the layers list itself
  does not change here — only `ignore_imports` shrinks.
- Future email features inherit the rule: domain event → signal receiver;
  scheduled nudge → comms beat sweep. No new blessed edges.
