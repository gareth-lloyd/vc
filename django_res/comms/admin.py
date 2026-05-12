from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest

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
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")


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
