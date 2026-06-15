from __future__ import annotations

from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payments"

    def ready(self) -> None:
        from core.audit import track
        from payments import signals
        from payments.models import Payment, Refund, SecurityDeposit

        signals._register()

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
        # SecurityDeposit: the full SD money lifecycle (pre-auth, capture,
        # claim, release), mirroring its `Payment`/`Refund` siblings. Track
        # status, the money columns, and the lifecycle stamps an auditor needs
        # to reconstruct a held/captured/released deposit; skip the chatty
        # `meta` JSON. No PII columns.
        track(
            SecurityDeposit,
            fields=[
                "status",
                "kind",
                "amount",
                "currency_id",
                "captured_amount",
                "refunded_amount",
                "damage_claim_id",
                "due_at",
                "hold_expires_at",
                "release_scheduled_for",
                "released_at",
                "requested_by_id",
                "failure_reason",
            ],
        )
