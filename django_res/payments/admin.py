"""Basic Django admin registrations for the payments app."""

from __future__ import annotations

from django.contrib import admin

from payments.models import (
    Payment,
    PaymentEvent,
    PaymentLine,
    Refund,
    SecurityDeposit,
    WebhookDelivery,
)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "booking", "purpose", "status", "amount", "due_at")
    list_filter = ("purpose", "status", "provider")
    search_fields = ("reference", "provider_reference")
    readonly_fields = ("reference", "settled_at", "created_at", "updated_at")


@admin.register(PaymentLine)
class PaymentLineAdmin(admin.ModelAdmin):
    list_display = ("payment", "description", "amount")
    search_fields = ("description",)


@admin.register(SecurityDeposit)
class SecurityDepositAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "booking",
        "kind",
        "status",
        "amount",
        "due_at",
        "release_scheduled_for",
    )
    list_filter = ("kind", "status")
    search_fields = ("reference",)
    readonly_fields = ("reference",)


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "booking",
        "purpose_track",
        "status",
        "amount",
        "requested_at",
    )
    list_filter = ("status", "purpose_track", "reason_code")
    search_fields = ("reference",)
    readonly_fields = ("reference",)


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "payment",
        "refund",
        "security_deposit",
        "from_status",
        "to_status",
        "kind",
        "source",
        "created_at",
    )
    list_filter = ("kind", "source")
    readonly_fields = tuple(
        f.name for f in PaymentEvent._meta.get_fields() if hasattr(f, "name") and not f.many_to_many
    )

    def has_delete_permission(self, request: object, obj: object | None = None) -> bool:
        # Append-only audit table — never deletable from the admin.
        return False


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider",
        "event_id",
        "signature_valid",
        "received_at",
        "processed_at",
    )
    list_filter = ("provider", "signature_valid")
    search_fields = ("event_id",)
    readonly_fields = tuple(
        f.name
        for f in WebhookDelivery._meta.get_fields()
        if hasattr(f, "name") and not f.many_to_many
    )
