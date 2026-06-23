# Q-017 — comms: signals-only sink, or move it down the spine?

- **Severity:** Question
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `pyproject.toml:188–216` (layers + blessed back-edges),
  `comms/signals.py`, `payments/tasks.py`

## Problem

`comms` sits at the **top** of the spine layers
(`comms > payments > reservations > …`), meaning nothing below may import
it — yet of the 7 blessed comms-bound back-edges in `ignore_imports`,
**5 are `payments.tasks → comms.*`**:

```toml
"payments.tasks -> comms.enums",
"payments.tasks -> comms.models",
"payments.tasks -> comms.exceptions",
"payments.tasks -> comms.recipients",
"payments.tasks -> comms.services",
```

(plus `accounts.services.password_reset -> comms.services` and
`reservations.urls -> comms.views`). Two competing email patterns coexist:
`comms/signals.py` registers receivers on domain signals (clean downward
edges, comms pulls), while `payments.tasks` and `accounts` call
`EmailService` directly (upward edges, individually blessed). Every new
email feature re-fights the "signal or direct call?" choice, and the
blessed-exception list grows each time the direct-call side wins.

## Decision needed

Pick one:

- **(a) Signals-only.** comms stays top-of-spine; migrate `payments.tasks`
  reminders (and the password-reset call) to fire domain signals that
  `comms/signals.py` consumes; prune the five back-edges.
- **(b) comms as a down-spine sink.** Move comms below `accounts`-adjacent,
  like `integrations` — domain apps reaching *down* into the email sink
  becomes a clean edge; `comms/signals.py`'s upward listening is then the
  part to unwind (or keep, since receivers on higher apps' signals are
  registered from comms's `ready()` via lazy imports).

(b) matches how the edges actually flow today; (a) matches the original
design intent. Either is workable — the cost is in not deciding.

## Acceptance

- Decision recorded in `django_res_design/10-decisions.md` and the layers
  rationale in `00-conventions.md` / `django_res/CLAUDE.md`.
- `pyproject.toml` layers + `ignore_imports` updated to match;
  `lint-imports` passes.

## Dependencies

Related: SMELL-015 (retry fix is independent of this decision). (FG-013 —
which edited the same layers list — has since landed in `done/`, so there is
no longer a coordination dependency; the `owners` app is already inside the
contract.)
