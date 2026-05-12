"""Admin registrations for the integrations app.

Token fields are masked — never display the cleartext access/refresh token.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from integrations.models import OAuthCredential, SyncIssue, SyncRecord, SyncRun


@admin.register(SyncRecord)
class SyncRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider",
        "content_type",
        "object_id",
        "status",
        "direction",
        "last_pushed_at",
        "last_pulled_at",
    )
    list_filter = ("provider", "status", "direction")
    search_fields = ("external_id",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(SyncRun)
class SyncRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider",
        "direction",
        "status",
        "started_at",
        "finished_at",
        "records_processed",
        "records_failed",
    )
    list_filter = ("provider", "status", "direction", "triggered_by")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SyncIssue)
class SyncIssueAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "kind", "severity", "resolved_at")
    list_filter = ("kind", "severity")
    readonly_fields = ("created_at", "updated_at")


@admin.register(OAuthCredential)
class OAuthCredentialAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider",
        "account_label",
        "is_active",
        "expires_at",
        "connected_at",
        "disconnected_at",
    )
    list_filter = ("provider", "is_active")
    readonly_fields = (
        "created_at",
        "updated_at",
        "access_token_masked",
        "refresh_token_masked",
    )
    exclude = ("access_token", "refresh_token")

    @admin.display(description="Access token")
    def access_token_masked(self, obj: OAuthCredential) -> str:
        return "***" if obj.access_token else ""

    @admin.display(description="Refresh token")
    def refresh_token_masked(self, obj: OAuthCredential) -> str:
        return "***" if obj.refresh_token else ""

    def get_readonly_fields(self, request: Any, obj: Any = None) -> tuple[str, ...]:
        # Token cleartext is never shown — admin sees the masked properties only.
        return self.readonly_fields
