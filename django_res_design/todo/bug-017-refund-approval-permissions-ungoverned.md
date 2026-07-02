# BUG-017 — Refund approval/execution perms are declared but granted to nobody; the SoD split is governed by ungoverned config

- **Severity:** 🔴 Bug (high priority — the refund approver/executor split is not actually enforceable by any tracked configuration)
- **Source:** the 2026-07-02 backend complexity audit (two authorization systems, no bridge)
- **Files:** `payments/models/refund.py:130–132` (Meta `permissions`:
  `approve_refund` / `execute_refund` / `self_approve_refund`),
  `payments/services/refund.py:50–52` (perm constants) + `:176–280`
  (`approve` / `execute` gated on `actor_has_perm(...)`),
  `core/api/permissions.py:63–74` (`actor_has_perm` → `user.has_perm()`),
  `:27–61` (`effective_staff_role`), `:108,140` (`IsReservationsWriter` /
  `IsAccountsWriter` — role-string boundary checks)

## Problem

The backend has **two authorization systems that never meet**:

- The **API boundary** authorises on `User.role` strings — `IsAccountsWriter`,
  `IsReservationsWriter`, `IsStaffRoleAdmin` via `effective_staff_role`
  (`core/api/permissions.py:27–154`).
- The **service layer** authorises on **native Django permissions** —
  `RefundService.approve/execute` require
  `actor_has_perm(actor, "payments.approve_refund")` /
  `"payments.execute_refund"` (`refund.py:50–52,176–280`), where
  `actor_has_perm` delegates to `user.has_perm()`
  (`permissions.py:63–74`). The perms are declared as model Meta permissions
  (`refund.py:130–132`; migration `0001`).

A wide grep finds **no production code that grants these perms to any
`StaffRole`** — no `assign_perm`, no Group provisioning, no
`user.user_permissions.set(...)` outside test fixtures/admin. The role world
(`StaffRole.ACCOUNTS`) and the Django-perm world
(`payments.approve_refund`) are wired independently and never bridged.

## Why it's a (high-priority) bug

The refund approver/executor separation-of-duties split (BUG-010's whole
point) is enforced by a permission set **no migration, seed, or Group
maintains**. Concretely, today:

- A user with `role=ACCOUNTS` passes `IsAccountsWriter` at the boundary but is
  **rejected** by `RefundService.approve` with `AuthorizationError`, unless a
  human has hand-clicked `payments.approve_refund` onto that user in Django
  admin. So refunds are un-approvable out of the box in any freshly-provisioned
  environment (prod/staging/CI/new hire), and
- if an admin *does* hand-assign perms, the SoD guarantee rests on manual,
  drift-prone, untracked per-user config rather than on the role model that
  the rest of the app authorises against.

Either way the money control is governed by ungoverned configuration — an
authorization correctness defect, not a style issue.

## Proposed fix

Pick one authority and bridge to it:

- **Preferred — provision role→permission Groups in a data migration:** a
  `payments` (or `accounts`) data migration creates Groups per `StaffRole` and
  assigns `approve_refund` / `execute_refund` / `self_approve_refund` to the
  right roles; user provisioning adds users to the Group for their role. The
  two layers can no longer diverge, and the grant is tracked in migrations.
- **Alternative — collapse to the role predicate:** replace the service-layer
  `has_perm` checks with the same `effective_staff_role`/`StaffRole` predicate
  the boundary uses, so there is one authorization vocabulary. (Loses Django's
  per-user perm granularity — only take this if that granularity isn't wanted.)

## Acceptance

- A freshly-migrated environment (no manual admin clicks) lets an
  `ACCOUNTS`-role user approve and a second role execute a refund, and blocks
  self-approve unless `self_approve_refund` is granted — proven by a test that
  provisions users via the normal role path only.
- No production authorization decision depends on per-user perms assigned by
  hand in admin.
- The role↔perm mapping lives in a migration/seed, not tribal knowledge.

## Dependencies

Directly affects BUG-010 (refund self-approve SoD) and GAP-057 (2FA refund
step-up — layers on the same approve/execute path). Related: SMELL-008
(service-layer contract single island). Independent of Q-024.
