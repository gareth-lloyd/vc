"""API v1 root — aggregates per-app URL modules."""

from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("", include("accounts.urls")),
    path("", include("properties.urls")),
    path("", include("pricing.urls")),
    path("", include("reservations.urls")),
    path("", include("payments.urls")),
    path("", include("integrations.urls")),
    path("", include("comms.urls")),
]
