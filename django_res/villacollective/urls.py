"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path, re_path

from core.views import spa_index

# Top-level URL prefixes owned by the server (API, admin) or by WhiteNoise
# (static assets, media — see `core.middleware.MediaWhiteNoiseMiddleware`),
# NOT by the SPA. The history fallback below must exclude them so an unmatched
# path under one of these — a bad API route, a missing static/media file —
# returns a real 404 instead of silently serving the SPA shell. Add any new
# server-/WhiteNoise-owned top-level prefix here.
NON_SPA_PREFIXES = ("api/", "admin/", "static/", "media/")
_SPA_FALLBACK = r"^(?!(?:{})).*$".format("|".join(NON_SPA_PREFIXES))

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("villacollective.api_urls")),
    # Smoke test
    path("api/", include("core.urls")),
    # Single-origin SPA history fallback — MUST stay last. Static assets, the
    # SPA build, and uploaded/seeded media are served by WhiteNoise ahead of
    # the URLconf, so only client-side routes reach this catch-all.
    re_path(_SPA_FALLBACK, spa_index, name="spa-index"),
]
