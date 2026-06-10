"""Generic webhook dispatch — persist-first + HMAC signature verification.

The contract:

1. `WebhookDispatcher.persist()` writes a `WebhookDelivery` row under the
   provider's `event_id`. Re-delivery raises `IntegrityError`; the caller
   surfaces the cached delivery instead of re-processing.
2. `WebhookDispatcher.verify_signature()` recomputes HMAC-SHA256 over the
   raw body bytes and compares with `hmac.compare_digest`. Verifying the
   re-encoded JSON would risk mismatches on whitespace/key ordering.
3. `WebhookDispatcher.process()` is the placeholder for the Celery task
   that loads the delivery, parses it through a provider-specific parser,
   and applies the resulting status transition. The synchronous shape
   here is intentional — production deployment swaps in a Celery
   `process_webhook_delivery.delay(delivery.id)` call.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from payments.models.webhook_delivery import WebhookDelivery

logger = structlog.get_logger(__name__)

# Webhook-layer transition policy — stricter than the model-level
# `PAYMENT_ALLOWED_TRANSITIONS`. A webhook may settle/fail/cancel only a
# payment that is still open, and refund only a settled one; the looser
# model-level seams (e.g. SUCCEEDED → CANCELLED for the SD supersede) are
# operator-only and not reachable from a provider event.
_WEBHOOK_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "succeeded": frozenset({"pending", "processing"}),
    "failed": frozenset({"pending", "processing"}),
    "cancelled": frozenset({"pending", "processing"}),
    "refunded": frozenset({"succeeded"}),
}


@dataclass
class ProviderEvent:
    """Normalised representation of a provider webhook event.

    Each provider's parser produces one of these. The dispatcher uses
    `payment_reference` (our `Payment.reference`) or `provider_reference`
    (the provider's transaction id) to find the target Payment.
    """

    event_kind: str
    payment_reference: str = ""
    provider_reference: str = ""
    amount: Decimal | None = None
    currency_code: str = ""
    settled_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class WebhookDispatcher:
    """Persist-first, signature-verifying webhook gateway."""

    @classmethod
    def persist(
        cls,
        *,
        provider: str,
        event_id: str,
        raw_body: bytes,
        headers: dict[str, str],
        signature: str,
    ) -> tuple[WebhookDelivery, bool]:
        """Write or fetch the persisted `WebhookDelivery`.

        Returns `(delivery, created)`. When `created` is False, the inbound
        is a replay — caller should return 200 with the prior outcome.
        """
        try:
            with transaction.atomic():
                delivery = WebhookDelivery.objects.create(
                    provider=provider,
                    event_id=event_id,
                    signature=signature,
                    raw_body=raw_body.decode("utf-8", errors="replace"),
                    headers=headers,
                    received_at=timezone.now(),
                )
            return delivery, True
        except IntegrityError:
            existing = WebhookDelivery.objects.get(
                provider=provider,
                event_id=event_id,
            )
            return existing, False

    @classmethod
    def reclaim(
        cls,
        delivery: WebhookDelivery,
        *,
        raw_body: bytes,
        headers: dict[str, str],
        signature: str,
    ) -> WebhookDelivery:
        """Overwrite a signature-invalid delivery with a verified re-send.

        Persist-first means a garbage POST can squat an `event_id` before the
        genuine provider delivery arrives (it gets a 401, but the row stays).
        When a *signature-valid* request later lands on that id, the stored
        garbage is replaced with the verified body and processing state is
        reset. Benign race: two concurrent reclaims are safe because
        `process()` is delivery-level idempotent.
        """
        delivery.raw_body = raw_body.decode("utf-8", errors="replace")
        delivery.headers = headers
        delivery.signature = signature
        delivery.signature_valid = True
        delivery.received_at = timezone.now()
        delivery.processed_at = None
        delivery.processing_error = ""
        delivery.save(
            update_fields=[
                "raw_body",
                "headers",
                "signature",
                "signature_valid",
                "received_at",
                "processed_at",
                "processing_error",
                "updated_at",
            ]
        )
        logger.info(
            "webhook.delivery_reclaimed",
            provider=delivery.provider,
            event_id=delivery.event_id,
            delivery_id=delivery.pk,
        )
        return delivery

    @classmethod
    def verify_signature(cls, *, provider: str, raw_body: bytes, signature: str) -> bool:
        """HMAC-SHA256 verification over the raw body bytes.

        The secret comes from `settings.PAYMENT_WEBHOOK_SECRETS[provider]`.
        An unknown provider or empty signature fails closed.
        """
        secrets = getattr(settings, "PAYMENT_WEBHOOK_SECRETS", {}) or {}
        # Accept both lower-case and upper-case provider keys to bridge the
        # `WebhookProvider` enum (lower) and any external configuration
        # that uses upper-case provider slugs.
        secret = secrets.get(provider) or secrets.get(provider.upper())
        if not secret or not signature:
            return False
        expected = hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @classmethod
    def process(cls, delivery: WebhookDelivery) -> None:
        """Apply the delivery's event to the target Payment.

        Synchronous; production wraps this in a Celery task. Idempotency is
        delivery-level: each row is processed at most once, and `processed_at`
        is set to short-circuit retries.
        """
        if delivery.processed_at is not None:
            return
        try:
            event = cls._parse(delivery)
            payment = cls._find_payment(event)
            if payment is None:
                delivery.processing_error = f"No Payment matched event {delivery.event_id!r}"
                logger.warning(
                    "webhook.no_payment_match",
                    provider=delivery.provider,
                    event_id=delivery.event_id,
                )
            else:
                cls._apply(payment, event, delivery)
                logger.info(
                    "webhook.processed",
                    provider=delivery.provider,
                    event_id=delivery.event_id,
                    payment_id=payment.pk,
                )
        except Exception as exc:
            delivery.processing_error = str(exc)
            # The contract is fail-soft (store the error, set processed_at, never
            # raise) — but a swallowed webhook error was previously invisible.
            logger.exception(
                "webhook.process_failed",
                provider=delivery.provider,
                event_id=delivery.event_id,
                error=str(exc),
            )
        delivery.processed_at = timezone.now()
        delivery.save(update_fields=["processed_at", "processing_error", "payment", "updated_at"])

    # ------------------------------------------------------------------
    # Helpers — provider-specific parsing dispatches per-provider.
    # ------------------------------------------------------------------
    @classmethod
    def _parse(cls, delivery: WebhookDelivery) -> ProviderEvent:
        if delivery.provider == "flywire":
            from payments.webhooks.flywire import parse_flywire_event

            return parse_flywire_event(delivery)
        raise ValueError(f"No parser registered for provider {delivery.provider!r}")

    @classmethod
    def _find_payment(cls, event: ProviderEvent) -> Any | None:
        from payments.models.payment import Payment

        if event.payment_reference:
            payment = Payment.objects.filter(reference=event.payment_reference).first()
            if payment is not None:
                return payment
        if event.provider_reference:
            return Payment.objects.filter(
                provider_reference=event.provider_reference,
            ).first()
        return None

    @classmethod
    def _apply(
        cls,
        payment: Any,
        event: ProviderEvent,
        delivery: WebhookDelivery,
    ) -> None:
        from payments.enums import EventSource, PaymentStatus

        delivery.payment = payment

        status_map = {
            "succeeded": PaymentStatus.SUCCEEDED.value,
            "failed": PaymentStatus.FAILED.value,
            "refunded": PaymentStatus.REFUNDED.value,
            "cancelled": PaymentStatus.CANCELLED.value,
        }
        event_kind = event.event_kind.lower()
        new_status = status_map.get(event_kind)
        if new_status is None:
            delivery.processing_error = (
                f"Unhandled event_kind {event.event_kind!r} for {payment.reference}"
            )
            return

        if payment.status == new_status:
            # Provider re-announced a state we already hold (e.g. a second
            # "paid" event with a fresh event_id). Clean idempotent no-op —
            # re-transitioning would re-fire the signal cascade.
            logger.info(
                "webhook.duplicate_event",
                provider=delivery.provider,
                event_id=delivery.event_id,
                payment_id=payment.pk,
                payment_status=payment.status,
            )
            return

        allowed_from = _WEBHOOK_ALLOWED_TRANSITIONS.get(event_kind, frozenset())
        if payment.status not in allowed_from:
            delivery.processing_error = f"out_of_order: {payment.status} -> {new_status}"
            logger.warning(
                "webhook.out_of_order",
                provider=delivery.provider,
                event_id=delivery.event_id,
                payment_id=payment.pk,
                payment_status=payment.status,
                event_kind=event_kind,
            )
            return

        if new_status == PaymentStatus.SUCCEEDED.value:
            amount_ok = event.amount is None or event.amount == payment.amount
            currency_ok = not event.currency_code or event.currency_code == payment.currency.code
            if not (amount_ok and currency_ok):
                # Partial or wrong-currency settlement: refuse to mark the full
                # payment paid. Partial-settlement support is future work.
                delivery.processing_error = (
                    f"amount_mismatch: expected {payment.amount} {payment.currency.code},"
                    f" got {event.amount} {event.currency_code}"
                )
                logger.warning(
                    "webhook.amount_mismatch",
                    provider=delivery.provider,
                    event_id=delivery.event_id,
                    payment_id=payment.pk,
                    expected_amount=str(payment.amount),
                    expected_currency=payment.currency.code,
                    amount=str(event.amount),
                    currency=event.currency_code,
                )
                return

        payment.transition_to(
            new_status,
            source=EventSource.WEBHOOK.value,
            delivery=delivery,
            payload_hash=hashlib.sha256(
                delivery.raw_body.encode("utf-8", errors="replace"),
            ).hexdigest(),
        )
