# Q-024 — Should cross-app money/lifecycle side-effects stay on domain signals, or move to explicit orchestration?

- **Severity:** ❓ Question (architecture direction — blocks how SMELL-020, BUG-015, GAP-061 are built)
- **Source:** the 2026-07-02 backend complexity audit (signals are load-bearing control flow)
- **Files:** `reservations/signals.py:32` (`booking_transitioned` def),
  `payments/signals.py:197–224` (`_close_money_on_booking_closed`),
  `:256–267` (receivers + `dispatch_uid` wiring),
  `payments/signals.py:64–72` (the "must run inside `transaction.atomic`"
  comment), `comms/signals.py:469–517` (comms subscribes to source-app
  signals), `data_migration/loaders/bookings.py:284` (disconnects a **private**
  payments receiver by name/uid)

## The question

The import spine forbids upward imports (`comms → payments → reservations →
… → accounts`), so every "point upward" interaction is done via Django
signals. That makes signals **load-bearing control flow**, not notification:

- One `Booking._transition` synchronously triggers payment-row creation, SD
  sizing, schedule close-out, and (guest + owner) email — spread across
  payments and comms receivers, ordered only by `dispatch_uid`.
- Atomicity is not owned by the mechanism: it depends on **every** caller
  wrapping the transition in `transaction.atomic` — self-documented as a
  comment (`payments/signals.py:64–72`: "A caller that drives the transition
  outside a transaction would commit the status change before this receiver
  runs — don't do that").
- A money-mutating receiver that raises rolls back the whole transition; a
  new transition entry point that forgets the atomic wrapper commits a status
  change with no payment schedule.
- The coupling is invisible to grep, mypy, and the import-linter — the real
  call graph lives in `.connect()` calls in `apps.ready()`, and the data
  loader already reaches into payments' **private**
  `_resync_schedule_on_booking_total_changed` by hardcoded name + uid to
  suppress it during bulk load (`bookings.py:284`).

comms is genuinely pull-only and defends itself (`_safe_send` swallows infra
errors), and GAP-058 already ratified that comms stays a signal subscriber.
The open question is narrower and about the **money** receivers:

**Do payment scheduling / SD sizing / schedule close-out stay as save-time
signal receivers, or move behind an explicit orchestration service that
`Booking._transition` calls directly (signals reserved for fire-and-forget
notification)?**

Sub-questions that need an answer before B/GAP-061/SMELL-020 land:

1. Is the money side-effect chain allowed to abort a status transition, or
   should the transition commit and the money work be a follow-on (outbox /
   task)?
2. Where does the atomicity contract live — enforced by a service boundary,
   or left as the current "wrap it yourself" convention?
3. Should the data loader depend on a **public, versioned** payments "suspend
   resync" hook instead of a private receiver name?

## Why it blocks other work

SMELL-020 (single money authority), BUG-015 (transition primitive), and
GAP-061 (SD sweep) all touch this chain. If the direction is "explicit
orchestration," those tickets should build the service seam rather than add
more receivers; if it's "keep signals," they should instead harden the
atomicity/ordering contract. Deciding once avoids building each the wrong way.

## Proposed options (for the decision)

- **A — Explicit orchestration:** a `BookingLifecycleService` (or method on
  `Booking._transition`) makes the money calls in-line and in a known order;
  signals keep only comms/notification. Money bugs become greppable and
  step-throughable; the "forgot atomic" footgun goes away. More upfront churn.
- **B — Keep signals, harden the contract:** keep receivers but (i) wrap the
  atomic boundary inside `_transition` itself so callers can't forget, (ii)
  expose a public suspend/resume hook for bulk loaders, (iii) document
  ordering as data, not comment. Cheaper, keeps the decoupling, but signals
  remain the hidden call graph.
- **C — Outbox:** transition commits; money/comms effects enqueue and run
  async. Strongest isolation, biggest build; probably v2.

## Dependencies

Decides the shape of SMELL-020, BUG-015, GAP-061. Aligns with GAP-058 (comms
pull-only) — this question is the payments-side counterpart. Related: FG-011,
FG-016 (bulk writes bypass signals — same mechanism).
