---
name: ship
description: >-
  Drive a big piece of work end-to-end through Gareth's disciplined cycle:
  worktree → plan → adversarial review of the plan → (user runs /compact) →
  execute in committable units with TDD → /code-review + action net-positive
  findings per unit → commit → merge to local main + clean up the worktree.
  USE WHEN the user invokes /ship <task or GAP-ticket>, or asks to "ship",
  "take this from plan to merge", or run the full cycle on a substantial change.
  SKIP for one-line fixes, questions, or anything that doesn't warrant a branch.
argument-hint: <task description or GAP-0XX ticket id>
disable-model-invocation: true
---

# /ship — full delivery cycle for a big piece of work

Orchestrate a substantial change from plan to merged. The work item is
**$ARGUMENTS** (a free-text task or a `django_res_design/todo/gap-0XX-*.md`
ticket). Run the phases **in order**. Halt at the marked gates.

This skill is **re-invocation-safe**: it can be stopped (e.g. for `/compact`)
and resumed. On every invocation, first run **Phase R** to figure out where you
are; only start from Phase 0 if there is no in-flight run.

The durable artifact that survives `/compact` and session restarts is the
**plan file** at `~/.claude/plans/ship-<slug>.md`. Keep its `## Progress`
section current — it is the single source of truth for "what's done".

---

## Phase R — Resume check (run first, every time)

1. Derive the `<slug>` from $ARGUMENTS (GAP id → `gap-0XX`; else a short
   kebab summary). If $ARGUMENTS is empty or literally `continue`, look for an
   existing `~/.claude/plans/ship-*.md` whose `## Progress` is unfinished and
   the matching `../villacollective-worktrees/<slug>/` worktree.
2. If a plan file + worktree already exist: read the plan, read `## Progress`,
   confirm the current branch/worktree, and **jump to the first unfinished
   phase/unit**. Tell the user where you're resuming. Do NOT redo finished units.
3. Otherwise start at Phase 0.

---

## Phase 0 — Worktree setup

1. Confirm you are in the primary repo (`/Users/garethlloyd/projects/villacollective`)
   and the working tree is clean (`git status`). If there are unrelated
   uncommitted changes, **halt and ask** how to proceed.
2. Create the worktree using the project convention (sibling dir, never nested):

   ```bash
   git worktree add -b feat/<slug> ../villacollective-worktrees/<slug> HEAD
   ```

3. Move the session into it. **Use `EnterWorktree` with an explicit `path`**
   pointing at `../villacollective-worktrees/<slug>` — its default is
   `.claude/worktrees/`, which violates the sibling convention and pollutes
   lint/test walks. From here on, **edit only through the worktree path**;
   main-repo paths land changes on the wrong branch.

---

## Phase 1 — Plan (in plan mode)

1. Call **`EnterPlanMode`** (read-only exploration; only the plan file may be written).
2. If $ARGUMENTS names a GAP ticket, read it first
   (`django_res_design/todo/gap-0XX-*.md`) plus `django_res_design/INDEX.md`
   and any files it references. Read `django_res/CLAUDE.md` /
   `frontend/CLAUDE.md` for stack conventions. **Delegate broad code reads to
   `Explore`/`general-purpose` subagents** so the main thread stays lean
   (you'll need that context budget to survive to merge).
3. Write the plan to **`~/.claude/plans/ship-<slug>.md`** with this structure:

   ```markdown
   # ship-<slug>: <title>

   ## Context        — problem, source ticket, key files (path:line)
   ## Key decisions  — choices made + why; alternatives rejected
   ## Units of work  — ordered, each independently committable:
       - Unit 1 — <name>: TDD steps (failing test first), files, gate scope
       - Unit 2 — …
   ## Deferred        — explicitly out of scope (so review doesn't re-raise it)
   ## Verification    — exact commands to prove each unit green
   ## Progress        — checklist of units; mark done + commit sha as you go
   ```

   Decompose aggressively — small units beat big landings (one logical unit
   per commit). Use `Write` to create the file (a first `Edit` on a not-yet-read
   file errors).

---

## Phase 2 — Adversarial review of the plan  ⛔ approval gate

1. Spawn a **`general-purpose` subagent** as an adversarial planning reviewer.
   Prompt shape (the phrasing that works):

   > You are an adversarial planning reviewer. Your job is to find what is
   > **WRONG, RISKY, or MISSING** in the plan — not to praise it. Read the plan
   > at `~/.claude/plans/ship-<slug>.md` first, then **verify its every claim
   > against the actual code** in `<worktree>/django_res` and
   > `<worktree>/frontend` and **cite file:line**. Flag BLOCKERs explicitly.
   > Check: wrong assumptions about existing code, missed edge cases, unit
   > ordering/dependency hazards, migration/data risks, test gaps, anything the
   > plan asserts that the code contradicts. Return findings ranked by severity.

2. **Bake the findings back into the plan file** (re-order/split units, add
   steps). For genuine forks in the road, ask the user via **`AskUserQuestion`**
   — don't guess on decisions that change the shape of the work.
3. Present the revised plan for approval with **`ExitPlanMode`**. If the user
   keeps planning, loop. Once approved, continue.

---

## Phase 3 — /compact  ⛔ HARD STOP (Claude cannot do this itself)

`/compact` is a **user-only** command — the assistant cannot invoke it, and you
cannot continue *after* it within the same turn (it clears context). So:

1. Make sure `## Progress` and all decisions are fully captured in the plan file
   (everything you'd need to resume from scratch).
2. **Stop and tell the user**, verbatim intent:
   *"Plan approved and saved to `~/.claude/plans/ship-<slug>.md`. Worktree:
   `../villacollective-worktrees/<slug>`. Run `/compact` now, then send
   `continue` (or re-run `/ship continue`) — I'll resume from the plan file at
   Phase 4."*
3. End the turn. (If the user prefers to skip the explicit compact and rely on
   auto-compaction, they'll just say "continue" — that's fine; the plan file
   makes it safe either way.)

---

## Phase 4–6 — Execute each unit (auto mode, high autonomy)

For **each unfinished unit** in the plan, in order, run 4→5→6 then update
`## Progress`. High autonomy; surface only genuine forks via `AskUserQuestion`.

### 4. Implement (TDD red → green → refactor)
- Write the failing test first, then the simplest code to pass, then refactor.
- For large units, **delegate the implementation to a subagent** with precise
  specs (cite the plan unit) and verify its output yourself — protects context.
- Run the quality gate **scoped to what changed**, never `--no-verify`:
  - Backend (in `<worktree>/django_res`): `uv run pytest <paths>`,
    `uv run ruff check`, `uv run ruff format --check .`, `uv run mypy .`
    (`--create-db` when migrations changed).
  - Frontend (in `<worktree>/frontend`): `npm test -- --run`, `npm run lint`,
    `npm run format:check`, `npm run typecheck`.
  - Or the bundled gate from the worktree root: `make lint` + `make test`.

### 5. /code-review this unit
- Invoke the **`code-review` skill** (via the `Skill` tool) at **high effort**
  on the unit's diff (`git diff HEAD` for staged work, or `main...HEAD`). High
  effort = recall-biased, multiple finder angles, ≤10 findings.
- **Triage each finding against the actual code — this is "net-positive":**
  - **Action** it only if it's a genuine improvement whose value clearly
    exceeds its churn: a real bug, a clear convention win (e.g. deep relative
    import → `@/` alias), dead-code / over-spec trim, or a type tightening
    (e.g. an `Any` that defeats mypy).
  - **Reject** the rest with a one-line, code-grounded reason: false positive,
    misunderstanding of the code, or a deliberately-scoped/deferred decision
    (cross-check the plan's `## Deferred`).
  - A clean review with nothing to action is a normal, good outcome.
- Apply accepted fixes; re-run the scoped gate.

### 6. Commit
- Conventional-commit subject with scope + ticket id, body explaining what/why
  plus a `Tests (TDD): …` line. Use a heredoc; **keep the env Co-Authored-By
  line**:

  ```bash
  git add -A && git commit -q -F - <<'EOF'
  feat(<scope>): GAP-0XX <unit> — <concise subject>

  <what & why; net-positive review changes actioned/rejected>
  Tests (TDD): <what was added/proven>

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  ```

- Mark the unit done + record the sha in the plan file's `## Progress`.
- **For very large work** you may, per your `/goal` cadence, re-plan + re-run a
  short adversarial review of the *next* unit before implementing it. Default:
  the up-front plan covers all units; only re-plan if reality diverges.

When all units are done and green, continue.

---

## Phase 7 — Merge to local main & clean up  ⛔ confirm before merging

We merge into **local `main` (no PRs), fast-forward only**, and push later in
batches — **do not push** unless the user asks.

1. Keep the branch fast-forwardable: in the worktree, `git merge main --no-edit`,
   resolve any conflicts, re-run the gate.
2. Confirm with the user, then merge from the **main checkout** (not the worktree):

   ```bash
   git -C /Users/garethlloyd/projects/villacollective merge --ff-only feat/<slug>
   ```

3. Clean up:

   ```bash
   cd /Users/garethlloyd/projects/villacollective
   git worktree remove ../villacollective-worktrees/<slug>
   git branch -d feat/<slug>
   git worktree list && git log --oneline -5   # verify
   ```

4. If the work closed a GAP ticket, do the close-out ritual: prepend a
   `> **✅ RESOLVED (2026-06-18)** — …` block and move the ticket to `done/`.
5. Report: units shipped, commits, review findings actioned vs rejected, and
   that the change is on local `main` (unpushed).

---

## Notes & known Claude Code limitations (see also the chat summary)

- **`/compact` can't be triggered by the skill** → Phase 3 is a hard stop. The
  plan file is what makes resuming safe.
- **`ExitPlanMode` needs user approval** every time — there's no auto-approve
  inside a skill. Same for the Phase 7 merge gate.
- **Context survival** drives the "delegate to subagents" rule throughout —
  subagents return summaries, keeping the main thread carrying only the plan +
  decisions across the whole cycle.
- **`EnterWorktree` default path** is wrong for this repo — always pass the
  explicit sibling `path`.
- Subagents don't see this session's history; pass them the plan-file path and
  exact file references rather than assuming shared context.
