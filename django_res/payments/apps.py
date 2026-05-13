from __future__ import annotations

from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payments"

    def ready(self) -> None:
        from core.audit import track
        from payments import signals  # noqa: F401
        from payments.models import Payment, Refund

        track(
            Payment,
            fields=[
                "status",
                "amount",
                "currency_id",
                "provider",
                "provider_reference",
                "payment_method",
                "due_at",
                "requested_at",
                "settled_at",
                "failure_reason",
            ],
        )
        track(
            Refund,
            fields=[
                "status",
                "amount",
                "currency_id",
                "purpose_track",
                "method",
                "reason_code",
                "approved_by_id",
                "approved_at",
                "rejected_by_id",
                "rejected_at",
                "rejection_reason",
                "executed_by_id",
                "executed_at",
                "cancelled_at",
                "settled_at",
                "failure_reason",
            ],
        )
