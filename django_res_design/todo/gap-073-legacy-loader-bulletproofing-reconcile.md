# GAP-073 — Legacy-loader bullet-proofing: land the remainder + branch reconciliation

- **Severity:** 🟨 Partial — a large hardening effort is complete and verified on a
  branch, but only one fix has landed on `main`; the rest needs reconciliation because
  `main` moved past the branch's base.
- **Source:** 2026-07-05/06 "make the data-migration legacy loader bullet-proof" effort
  on the `feat/legacy-loader` worktree (branched from `b3abc0e`). Full narrative in
  `django_res/data_migration/DRYRUN_LOG.md`, `ACCEPTANCE.md`, `COVERAGE.md`.
- **Branch:** `feat/legacy-loader` (commits `d92503d` docs + `4c01b7b` code), **unmerged,
  unpushed**. Worktree retained (not cleaned up) because ~half the branch is superseded and
  the mergeable half needs rework.

## What was done on the branch (verified green: `loadlegacy --all` exit 0 / 0 errors,
`reconcile_legacy --integrations` exit 0 / all checks OK, idempotent double-run, 279
data_migration tests, ruff/mypy/import-linter clean)

- **Standards:** `ACCEPTANCE.md` (S1–S7: coverage → recoverability), `COVERAGE.md` (all 60
  live tables classified — none unaccounted for), `DRYRUN_LOG.md` (run-by-run defect log).
- **6 defects fixed** (two silent data-loss):
  1. Zoho backfill crashed the whole run on missing `ZohoId` columns → INFORMATION_SCHEMA
     probe + skip/annotate + per-loader crash isolation in `loadlegacy`.
  2. `IsDefault*` property/finance defaults never resolved (min-nights ×197, commission
     ×68, currency ×91 loading wrong).
  3. Commission/deposit type maps keyed on wrong legacy codes.
  4. `guest_preference` registry-order bug (only converged on a 2nd run).
  5. PersonEmail/Phone reconcile client-slice off by 30.
  6. RateBand `expected_gap` placeholder → itemised **3805**.
- **Role-code fidelity bug** (see below) — the one piece **already landed on `main`**.
- **New capability:** `availability_block` loader (future non-available runs → `BookingHold`).
- **Four product decisions (2026-07-06, all resolved):**
  1. **Temenos** shared ZohoId → accept (two distinct villas, source-side Zoho error);
     deterministic `ORDER BY Id` link, gap 1, flag CRM.
  2. **Web copy** → preserve: new `WEB_DESCRIPTION`/`LOCATION` description sections +
     `Property.video_url` (271/253/29 loaded live).
  3. **Property POA** → deferred (18 villas; regression risk tracked in CUTOVER §4h).
  4. **VillaContactGroupMap** → expand 38 net-new contact→property links into
     `PropertyContactAssignment`.

## Landed on `main`

- **Role-code fix** — `_ROLE_MAP` re-keyed on the VillaRoles **Code** (10/20/40/50/80),
  not the Id (1–5). The role FK in the dump stores the Code, so the old map fell through
  to the OWNER fallback for every row, flattening **~197/335** `PropertyContactAssignment`
  roles (all Agents, Villa Admins, Villa Managers, Management Companies) to Owner. This bug
  was live on `main` (the property-contact assignment loader survived GAP-070). Fixed +
  test updated, committed on `main` (hooks green).

## Why the branch can't just be merged (the reconciliation)

`feat/legacy-loader` was cut from `b3abc0e`; `main` has since merged:
- **GAP-070** — deleted `PropertyGroup`/`GroupSettings`/`GroupFinance` and removed
  `PropertyGroupLoader`/`GroupFinanceLoader` from `data_migration`. The branch still has
  those loaders + `test_group_finance_loader.py` (modify/delete conflict); its
  finance-defaults work targets the now-deleted `GroupFinance`.
- **GAP-065** — room-location (floor + `placement_note` + blank placement, `properties/0029`)
  is already done. The branch re-implements a subset → content conflicts in `rooms.py`,
  `enums.py`, `property_children.py` + **migration-number collision** (both have
  `properties/0029` and `0030`).
- Plus BUG-016 / GAP-072.

`git merge-tree` shows 7 content conflicts + 1 modify/delete; `registry.py` and
`reconcile_legacy.py` auto-merge textually but break semantically (they'd import deleted
loaders).

## Next steps (needs an owner decision — asked, no response yet)

1. **Salvage-only (recommended, lower risk):** re-apply the still-valid,
   group/placement-independent work as fresh commits on `main`: Zoho/Temenos fix,
   `loadlegacy` crash isolation, RateBand calibration, `availability_block` loader,
   web-copy preservation, reconcile hardening, + the standards docs. Drop the superseded
   GAP-065 placement and the group loaders.
2. **Full reconciliation rebase:** rebase the branch onto `main`, resolving every conflict
   — drop my GAP-065 placement (main's wins), rework the group loaders + GroupMap-expansion
   for the post-GAP-070 world, adapt finance-defaults to `PropertyDefaults`. Preserves the
   most but conflict-heavy.
3. **GroupMap (decision 4) open question:** post-GAP-070 the product has no groups, but the
   dump still has `VillaContactGroupMap`. The 38 net-new contact→property links are real
   data; expansion reads legacy group tables and writes `PropertyContactAssignment` (needs
   no `PropertyGroup` model), so it can be rebuilt — or dropped (19 edges recoverable from
   the archived dump). Owner call.

## Related open items (not blockers)

- **FE cutover blocker:** `frontend/src/features/properties/schemas.ts` zod
  `ROOM_PLACEMENTS` must accept the new placement values + blank `""` before placement data
  lands (independent of this ticket; noted in DRYRUN_LOG).
- **Deferred:** property-level POA flag (18 villas) — CUTOVER §4h.
