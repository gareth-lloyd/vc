from __future__ import annotations

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self) -> None:
        from accounts import signals  # noqa: F401
        from accounts.models import Contact
        from core.audit import track

        track(
            Contact,
            fields=[
                "title",
                "first_name",
                "last_name",
                "company",
                "address_line_1",
                "address_line_2",
                "notes",
                "status",
            ],
        )
