"""Root URL configuration."""

from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("api/", include("core.urls")),
]
