# GAP-122 — `ensure_staff_superusers`: a real command for staging/prod logins

**Severity:** gap (ops; the current route is a shell one-liner that leans on
seed-data internals).

**Status:** ⬜ filed 2026-09-22, spun off GAP-120.

**Source:** GAP-120. After the legacy restore scrubbed every password on
staging, the four staff accounts were re-created with

```
python manage.py shell -c "
from getpass import getpass
from seeding.stages.users import _SUPERUSERS, _ensure_superuser
for email, _pw, first, last, _tfa in _SUPERUSERS:
    _ensure_superuser(email, getpass(f'New password for {email}: '), first, last, None)
"
```

It worked, but it imports two underscored names from the dev-seeding package,
and `_SUPERUSERS` carries the **hardcoded dev passwords** next to the emails
— one slip (`_pw` instead of `getpass`) and the repo-committed passwords are
live on a database of real client data. `seed_dev` itself is rightly blocked
on staging (`SEED_DEV_ALLOWED` only under `dev`/`test`… and `staging.py`,
which GAP-120 says must never be used there again).

## Proposal

A management command in `accounts` (not `seeding`):

```
python manage.py ensure_staff_superusers            # prompts per user
python manage.py ensure_staff_superusers --from-env # STAFF_PASSWORD_<slug>
```

- The **staff list** (email, first, last) moves out of `seeding.stages.users`
  into a plain constant `seeding` imports too — `accounts/staff.py` or
  settings — so both paths share one source of who the staff are.
- **Passwords never live in the repo.** Interactive `getpass` by default; the
  `--from-env` form reads `STAFF_PASSWORD_GLLOYD` etc. so Render's
  `preDeployCommand` or a one-off job can run it without a terminal. Missing
  var ⇒ that user is created (or left) with an **unusable** password, never a
  default.
- Idempotent: existing user keeps its id and profile, gets `is_staff`,
  `is_superuser`, `is_active` set and the password replaced only when one was
  supplied. Reuse `_ensure_superuser`'s body, un-underscored.
- TFA: no dev secret outside `dev`/`test`; on staging/prod the user enrols on
  first login (`TFA_ENFORCED`).
- `seeding.stages.users` becomes a thin caller that passes the dev passwords.

## Acceptance

- The seed stage and the new command share one staff list.
- `grep -r '<any dev password>' django_res/accounts` finds nothing.
- Tests: creates when absent, updates when present, unusable password when no
  password given, refuses nothing (it is safe on every environment).
- GAP-120's recipe step "createsuperuser" points at this command.
