"""Payments URL routes — currently the webhook ingest surface."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, path

from payments.views import webhook_view

urlpatterns: list[URLPattern | URLResolver] = [
    path(
        "webhooks/payments/<str:provider_slug>/",
        webhook_view,
        name="payments-webhook",
    ),
]
