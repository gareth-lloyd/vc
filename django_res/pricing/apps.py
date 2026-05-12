from __future__ import annotations

from django.apps import AppConfig


class PricingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pricing"

    def ready(self) -> None:
        from pricing import signals  # noqa: F401
