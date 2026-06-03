---
description: Run the Django + Vite dev servers for the CURRENT worktree to demo its work — stops any other running servers, brings up the DB, applies migrations, then starts both servers in the background.
argument-hint: "[--seed]   (optional: seed dev data if the DB looks empty)"
allowed-tools: Bash, Read, BashOutput, KillShell
---

Goal: stand up a working demo of **this worktree's** branch — Django API + Vite SPA
— so the user can click through the changes in a browser.

Run everything from the **current working directory** (the worktree you were invoked
in). Do NOT `cd` into the main checkout. The repo layout is `django_res/` (backend)
and `frontend/` (SPA), with `docker-compose.yml`, `Makefile`, and `logs/` at the
worktree root.

Important shared-state facts (all worktrees share these):

- The Postgres dev DB is a **single** docker container (`villacollective-db`, host
  port `55432`, volume `villa_pgdata`). Every worktree connects to the same DB, so
  migrations and seed data you apply here are visible to all branches. Mention this
  if the branch has migrations that other branches don't — switching back later may
  need a `migrate` on the other branch.
- Ports **8000** (Django) and **5173** (Vite, fixed) are the contention point. Only
  one worktree can serve them at a time, which is why step 1 stops strays.

Work the steps in order. After each command, check the output before moving on; if
something fails, stop and report it rather than pushing ahead.

## 1. Stop any other running servers

Free the ports so this worktree's servers can bind. These kills are best-effort —
a "no process found" is fine, not an error.

```bash
# Django dev servers (runserver autoreload spawns a child; match both).
pkill -f "manage.py runserver" 2>/dev/null || true
# Vite dev servers.
pkill -f "node.*vite" 2>/dev/null || true
# Anything still holding the two ports (covers servers started outside make/pkill).
lsof -ti tcp:8000 2>/dev/null | xargs -r kill 2>/dev/null || true
lsof -ti tcp:5173 2>/dev/null | xargs -r kill 2>/dev/null || true
```

Also stop any dev-server shells **you** started earlier in this session (check your
background shells and `KillShell` them) so logs don't interleave across runs.

Then confirm both ports are free:

```bash
lsof -i tcp:8000 -i tcp:5173 || echo "ports 8000 + 5173 are free"
```

If a port is still held after this, surface what's holding it (`lsof -i tcp:8000`)
and ask before force-killing anything you didn't start.

## 2. Bring up the database

```bash
docker compose up -d db
```

Wait for it to be healthy before migrating (the container has a `pg_isready`
healthcheck):

```bash
for i in $(seq 1 30); do
  docker compose exec -T db pg_isready -U villa -d villacollective >/dev/null 2>&1 && { echo "db ready"; break; }
  sleep 1
done
```

If `docker compose up` fails because the Docker daemon isn't running, tell the user
to start Docker Desktop (suggest they run `! open -a Docker`) and stop here.

## 3. Apply all migrations

```bash
cd django_res && uv run python manage.py migrate
```

Report whether any migrations were actually applied (vs. "No migrations to apply").
If `makemigrations --check` would flag model changes without a migration, note it —
but do NOT generate migrations as part of a demo unless the user asks.

## 4. (Optional) Seed dev data

Only if the user passed `--seed`, OR the DB has no properties to demo against
(quick check below). Seeding is idempotent-ish but writes to the shared DB.

```bash
cd django_res && uv run python manage.py shell -c "from properties.models import Property; print('properties:', Property.objects.count())"
```

If they asked to seed (or the count is 0 and a demo needs data):

```bash
cd django_res && uv run python manage.py seed_dev
```

## 5. Start both servers (background)

Use the Makefile targets — they tee output to `logs/django.log` and `logs/vite.log`
so you can tail them. Start each as a **background** shell from the worktree root:

```bash
make dev-backend      # run_in_background: true  → Django on http://127.0.0.1:8000
make dev-frontend     # run_in_background: true  → Vite   on http://localhost:5173
```

(If `make` isn't available, fall back to `cd django_res && uv run python manage.py
runserver` and `cd frontend && npm run dev`, each backgrounded.)

## 6. Confirm they came up

Give each a few seconds, then check the logs / a health probe rather than assuming:

```bash
sleep 4
curl -sS -o /dev/null -w "backend %{http_code}\n" http://127.0.0.1:8000/api/ || echo "backend not responding yet"
curl -sS -o /dev/null -w "frontend %{http_code}\n" http://localhost:5173/ || echo "frontend not responding yet"
```

If the frontend log shows `node_modules` missing, run `cd frontend && npm ci` once,
then restart `dev-frontend`. If the backend log shows a DB connection error, the DB
isn't healthy yet — recheck step 2.

## 7. Report

Tell the user, concisely:

- **Which worktree/branch** is now serving (run `git branch --show-current`).
- The two URLs: **API → http://127.0.0.1:8000**, **SPA → http://localhost:5173**
  (open the SPA URL to demo; it proxies `/api` and `/media` to the backend).
- That both servers are running in the background and how to watch them
  (`make logs`), and that re-running this command from another worktree will stop
  these and take over the ports.
- A one-line pointer to **what this branch changed** so they know what to click
  through (derive from the branch name / recent commits).
