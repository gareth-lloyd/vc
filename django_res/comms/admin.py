from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from comms import tasks
from comms.enums import EmailLogStatus
from comms.models import EmailLog, EmailTemplate, SmtpProfile


@admin.register(SmtpProfile)
class SmtpProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "scope", "owner", "host", "from_email", "is_active")
    list_filter = ("scope", "is_active")
    search_fields = ("name", "from_email", "host", "username")
    # Never surface the encrypted password in the admin UI; rotate via a
    # dedicated action on the profile (test-send / re-encrypt) rather than
    # echoing the stored ciphertext.
    exclude = ("encrypted_password",)
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("key", "version", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("key", "subject_template")
    readonly_fields = (
        "body_template_html",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = (
        "template_key",
        "template_version",
        "status",
        "from_email",
        "queued_at",
        "sent_at",
    )
    list_filter = ("status", "template_key")
    search_fields = ("template_key", "rendered_subject", "from_email")
    readonly_fields = tuple(f.name for f in EmailLog._meta.get_fields() if hasattr(f, "attname"))
    actions = ("resend_blocked_or_failed",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: EmailLog | None = None,
    ) -> bool:
        # Logs are append-only; allow viewing only.
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: EmailLog | None = None,
    ) -> bool:
        return False

    @admin.action(description="Re-send selected BLOCKED or FAILED logs")
    def resend_blocked_or_failed(
        self,
        request: HttpRequest,
        queryset: QuerySet[EmailLog],
    ) -> None:
        retriable = (EmailLogStatus.FAILED, EmailLogStatus.BLOCKED)
        eligible = queryset.filter(status__in=retriable)
        skipped = queryset.exclude(status__in=retriable).count()
        log_ids = list(eligible.values_list("pk", flat=True))

        if log_ids:
            eligible.update(status=EmailLogStatus.QUEUED, failure_reason="")
            for log_id in log_ids:
                tasks.send_email_log.delay(log_id)  # type: ignore[attr-defined]
            self.message_user(
                request,
                f"Re-queued {len(log_ids)} log(s) for delivery.",
                level=messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f"Skipped {skipped} log(s) that were not BLOCKED or FAILED.",
                level=messages.WARNING,
            )
