"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path, re_path

from core.views import spa_index

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("villacollective.api_urls")),
    # Smoke test
    path("api/", include("core.urls")),
    # Single-origin SPA history fallback — MUST stay last. The negative
    # lookahead keeps API/admin/static 404s as real 404s rather than
    # silently returning the SPA shell.
    re_path(r"^(?!api/|admin/|static/).*$", spa_index, name="spa-index"),
]
