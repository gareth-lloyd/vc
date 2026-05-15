# Single-origin image: Django serves the API *and* the built SPA, so there
# is no CORS / cross-site-cookie surface. Multi-stage: Node builds the SPA,
# Python runs Django; only the built bundle crosses the stage boundary.

# ---- Stage 1: build the Vite SPA -------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# No VITE_API_BASE_URL -> the client falls back to a relative "" base, so it
# calls /api/v1 on whatever origin serves it (i.e. this same service).
RUN npm run build

# ---- Stage 2: Django app ---------------------------------------------------
FROM python:3.13-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

RUN pip install --no-cache-dir uv

# Dependency layer (cached unless lockfile changes).
COPY django_res/pyproject.toml django_res/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY django_res/ ./
COPY --from=frontend /frontend/dist ./frontend_dist

# collectstatic runs under dev settings: it only needs STATIC_* (all in
# base) and avoids requiring the production secrets at image-build time.
# Runtime settings come from DJANGO_SETTINGS_MODULE in render.yaml.
RUN DJANGO_SETTINGS_MODULE=villacollective.settings.dev \
    python manage.py collectstatic --noinput

# $PORT / $WEB_CONCURRENCY are injected by Render at runtime — shell form so
# they expand.
CMD ["sh", "-c", "gunicorn villacollective.wsgi:application --bind 0.0.0.0:$PORT --workers ${WEB_CONCURRENCY:-2}"]
