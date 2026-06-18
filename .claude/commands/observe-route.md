---
description: Drive a frontend route with the Playwright MCP and report repeated API requests / flapping components, using the DEV-only observability layer (window.__rqLog / __renderLog).
argument-hint: "<route> e.g. /properties or /bookings/123 (defaults to /)"
allowed-tools: mcp__playwright__browser_navigate, mcp__playwright__browser_evaluate, mcp__playwright__browser_network_requests, mcp__playwright__browser_console_messages, mcp__playwright__browser_click, mcp__playwright__browser_type, mcp__playwright__browser_fill_form, mcp__playwright__browser_snapshot, mcp__playwright__browser_wait_for, Read
---

Goal: observe **$ARGUMENTS** (default `/`) running in the real browser and report any
repeated/looping API requests or flapping (over-rendering) components.

This relies on the DEV-only observability layer. Read
`frontend/src/lib/devtools/README.md` first — it owns the `window` globals, the
`browser_evaluate` reader snippets, and the heuristics/thresholds. Use those exact
readers; do not reinvent them.

Prerequisite (do NOT start servers yourself — ask the user to run `/demo-worktree`
if they're not up): the Vite SPA on `http://localhost:5173`, Django on `:8000`, DB
up. The dev build exposes `window.__rqLog`, `window.__rqClient`, `window.__mutLog`,
`window.__renderLog`, and `window.__rqReset()`.

Steps:

1. `browser_navigate` → `http://localhost:5173`. If redirected to `/login`, log in
   with `glloyd@gmail.com` / `fiery-kite-pumpkin-eton` (use `browser_snapshot` to
   find the fields, then `browser_fill_form` / `browser_type` + `browser_click`).
   Confirm `window.__rqClient` exists via `browser_evaluate` `() => !!window.__rqClient`
   — if it's missing, the build isn't DEV or the observer didn't install; stop and say so.
2. `browser_navigate` → the target route.
3. **Reset buffers**: `browser_evaluate` → `() => window.__rqReset?.()`.
4. **Idle baseline**: `browser_wait_for` ~3s with NO interaction. Then run reader (1)
   `{n:3, windowMs:5000}` and reader (3) `{windowMs:5000}` — anything flagged here is
   a zero-interaction loop (the worst kind).
5. **Interact**: `browser_snapshot`, then `browser_click` / `browser_type` the main
   affordances on the route (open a dialog, type in a filter/preview field, switch a
   tab). Keep it representative, not exhaustive.
6. `browser_wait_for` ~5s.
7. **Collect**: `browser_network_requests` (count requests per `/api/v1/...` path),
   readers (1)–(4) from the README, and `browser_console_messages` (grep for
   "Maximum update depth exceeded" and React warnings).

Report, concisely:

- **Repeated requests**: any query key fetched > 3× in 5s, or any endpoint hit > N×;
  name the `queryHash` / endpoint and whether it fired during idle or only on
  interaction. Cross-check `__mutLog` for an `invalidate` wave that triggered a fetch
  storm.
- **Flapping**: any Profiler `id` whose commit count climbs while idle, repeated
  `nested-update` phases, or a "Maximum update depth exceeded" console error.
- **Verdict**: clean, or a specific suspect with the evidence (counts + timing) and
  the likely cause (e.g. unstable object in a query key, broad invalidation,
  `refetchOnWindowFocus`). Do not speculate beyond what the buffers show.
