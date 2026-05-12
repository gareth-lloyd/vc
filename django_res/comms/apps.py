from __future__ import annotations

from django.apps import AppConfig


class CommsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "comms"

    def ready(self) -> None:
        from comms import signals

        signals._register()
