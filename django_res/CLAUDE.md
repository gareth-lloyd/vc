# Django REST API

## Local setup

1. `docker compose up -d` (from repo root) — starts Postgres at `localhost:55432`.
2. `cp .env.example .env` (or export `DATABASE_URL` directly).
3. `uv sync`
4. `uv run python manage.py migrate`
5. `uv run pytest` — tests run against the same Postgres instance
   (pytest-django creates and drops `test_villacollective` automatically).

## Principles

1. This is a Django REST framework app to support the Villa Collective management suite.

2. **Off-the-shelf over bespoke.** Reach for established libraries (DRF,
   `django-filter`, `dj-rest-auth` / `django-allauth`, `factory-boy`,
   etc.) before writing custom

3. Layered architecture:

- DRF handles serialization and deserialization from HTTP
- ALL business logic needs to be OUTSIDE of the view code, in its own service layer

django_res
./<app>
./services/<service name>
./models/<model name>
./views/<view name>
./tests/

4. One model per file in <app>/models/\*
