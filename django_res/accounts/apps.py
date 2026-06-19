from __future__ import annotations

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self) -> None:
        from accounts import signals  # noqa: F401
        from accounts.models import Person, User
        from core.audit import track

        track(
            Person,
            fields=[
                "title",
                "first_name",
                "last_name",
                "company",
                "address_line_1",
                "address_line_2",
                "town",
                "post_code",
                "marketing_consent",
                "notes",
                "status",
                "kind",
            ],
        )
        # User auth/role/2FA changes — record what shifted, never the
        # cleartext secret. Password rotations are caught by Django's own
        # auth machinery; we deliberately skip the hash here.
        track(
            User,
            fields=[
                "email",
                "phone",
                "role",
                "is_active",
                "is_staff",
                "is_superuser",
                "tfa_method",
                "tfa_secret",
                "tfa_enrolled_at",
                "last_login_ip",
                "preferred_language",
            ],
            sensitive=["tfa_secret"],
        )
