"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("villacollective.api_urls")),
    # Smoke test
    path("api/", include("core.urls")),
]
