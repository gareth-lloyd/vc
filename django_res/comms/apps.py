from __future__ import annotations

from django.apps import AppConfig


class CommsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "comms"

    def ready(self) -> None:
        from comms import signals
        from comms.models import EmailLog, EmailTemplate, SmtpProfile
        from core import audit

        signals._register()

        audit.track(
            EmailTemplate,
            fields=(
                "key",
                "version",
                "subject_template",
                "body_template",
                "body_template_mjml",
                "is_active",
                "notes",
            ),
        )
        audit.track(
            SmtpProfile,
            fields=(
                "name",
                "scope",
                "owner_id",
                "host",
                "port",
                "username",
                "encrypted_password",
                "use_tls",
                "from_email",
                "reply_to",
                "is_active",
            ),
            sensitive=("encrypted_password",),
        )
        audit.track(
            EmailLog,
            fields=(
                "status",
                "smtp_profile_id",
                "from_email",
                "to",
                "rendered_subject",
                "rendered_body",
                "rendered_body_html",
                "failure_reason",
                "sent_at",
            ),
            sensitive=("rendered_subject", "rendered_body", "rendered_body_html"),
        )
