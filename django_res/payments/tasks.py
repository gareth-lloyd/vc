"""Background-task entry points for the payments app.

All tasks are written synchronously today; production deployment swaps in
Celery decorators (`@shared_task`) and `*.delay(...)` enqueuing.
"""

from __future__ import annotations

from payments.models.webhook_delivery import WebhookDelivery
from payments.webhooks.base import WebhookDispatcher


def process_webhook_delivery(delivery_id: int) -> None:
    """Load a persisted delivery and apply its event.

    TODO: convert to a Celery `@shared_task` with autoretry on transient
    exceptions and a Sentry alert after retry exhaustion.
    """
    delivery = WebhookDelivery.objects.get(pk=delivery_id)
    WebhookDispatcher.process(delivery)


def send_payment_reminders() -> None:
    """Per-purpose reminder logic (deposit due, balance 7-day warning,
    balance due, SD due). Idempotency lives in the comms `EmailLog`
    correlation lookup — no `Payment.reminder_sent_at` column.

    TODO: implement reminder scheduling; emits signals consumed by `comms`.
    """


def process_sd_refunds() -> None:
    """Walk `SecurityDeposit` rows due for release / refund.

    PRE_AUTH_HOLD past `release_scheduled_for` → `:release` the hold.
    BT_REFUNDABLE past `release_scheduled_for` → open + execute a
    `Refund(purpose_track=SECURITY_DEPOSIT)`.

    TODO: implement the scan + dispatch loop. Flagged for ops review if a
    damage claim is pending against the booking.
    """
