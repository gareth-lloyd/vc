"""Tests for the webhook dispatcher — idempotency + signature verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any

import pytest
from django.conf import settings

from payments.enums import PaymentPurpose, PaymentStatus
from payments.models import Payment, WebhookDelivery
from payments.webhooks.base import WebhookDispatcher


def _flywire_secret() -> str:
    return settings.PAYMENT_WEBHOOK_SECRETS["FLYWIRE"]


def _sign(body: bytes) -> str:
    return hmac.new(_flywire_secret().encode("utf-8"), body, hashlib.sha256).hexdigest()


@pytest.fixture
def pending_payment(db: None, booking: Any, gbp: Any) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        status=PaymentStatus.PENDING.value,
        amount=Decimal("420.00"),
        currency=gbp,
    )


@pytest.mark.django_db
def test_persist__duplicate_event_id_returns_existing(db: None) -> None:
    body = b'{"event_id": "ev-1"}'
    d1, c1 = WebhookDispatcher.persist(
        provider="flywire",
        event_id="ev-1",
        raw_body=body,
        headers={},
        signature="x",
    )
    assert c1 is True

    d2, c2 = WebhookDispatcher.persist(
        provider="flywire",
        event_id="ev-1",
        raw_body=body,
        headers={},
        signature="x",
    )
    assert c2 is False
    assert d1.pk == d2.pk
    assert WebhookDelivery.objects.count() == 1


@pytest.mark.django_db
def test_verify_signature__valid_body(db: None) -> None:
    body = b'{"event_id":"ev-2"}'
    sig = _sign(body)
    assert WebhookDispatcher.verify_signature(
        provider="FLYWIRE",
        raw_body=body,
        signature=sig,
    )


@pytest.mark.django_db
def test_verify_signature__rejects_tampered_body(db: None) -> None:
    sig = _sign(b'{"event_id":"ev-3"}')
    assert not WebhookDispatcher.verify_signature(
        provider="FLYWIRE",
        raw_body=b'{"event_id":"ev-3-tampered"}',
        signature=sig,
    )


@pytest.mark.django_db
def test_verify_signature__rejects_unknown_provider(db: None) -> None:
    assert not WebhookDispatcher.verify_signature(
        provider="unknown",
        raw_body=b"{}",
        signature="anything",
    )


@pytest.mark.django_db
def test_process__advances_payment_to_succeeded(
    pending_payment: Payment,
) -> None:
    body = json.dumps(
        {
            "event_id": "ev-success-1",
            "event_type": "paid",
            "payment_reference": pending_payment.reference,
            "amount": "420.00",
            "currency": "GBP",
        }
    ).encode("utf-8")
    delivery, _ = WebhookDispatcher.persist(
        provider="flywire",
        event_id="ev-success-1",
        raw_body=body,
        headers={},
        signature=_sign(body),
    )
    WebhookDispatcher.process(delivery)

    pending_payment.refresh_from_db()
    delivery.refresh_from_db()
    assert pending_payment.status == PaymentStatus.SUCCEEDED.value
    assert delivery.processed_at is not None
    assert delivery.processing_error == ""


@pytest.mark.django_db
def test_process__deposit_webhook_advances_booking(
    pending_payment: Payment,
) -> None:
    """End-to-end: a settled deposit webhook leaves the Booking DEPOSIT_PAID."""
    from reservations.enums import BookingStatus

    booking = pending_payment.booking
    assert booking.status == BookingStatus.AWAITING_DEPOSIT.value

    body = json.dumps(
        {
            "event_id": "ev-advance-1",
            "event_type": "paid",
            "payment_reference": pending_payment.reference,
            "amount": "420.00",
            "currency": "GBP",
        }
    ).encode("utf-8")
    delivery, _ = WebhookDispatcher.persist(
        provider="flywire",
        event_id="ev-advance-1",
        raw_body=body,
        headers={},
        signature=_sign(body),
    )
    WebhookDispatcher.process(delivery)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.DEPOSIT_PAID.value


# ----------------------------------------------------------------------
# _apply hardening — delivery↔payment linkage, amount/currency checks,
# duplicate and out-of-order events.
# ----------------------------------------------------------------------


def _deliver(event_id: str, **body_fields: Any) -> WebhookDelivery:
    """Persist + process one signed Flywire delivery; return the delivery."""
    body_dict: dict[str, Any] = {"event_id": event_id, "event_type": "paid"}
    body_dict.update(body_fields)
    body = json.dumps(body_dict).encode("utf-8")
    delivery, _ = WebhookDispatcher.persist(
        provider="flywire",
        event_id=event_id,
        raw_body=body,
        headers={},
        signature=_sign(body),
    )
    WebhookDispatcher.process(delivery)
    delivery.refresh_from_db()
    return delivery


@pytest.mark.django_db
def test_process__links_delivery_to_payment(pending_payment: Payment) -> None:
    delivery = _deliver(
        "ev-link-1",
        payment_reference=pending_payment.reference,
        amount="420.00",
        currency="GBP",
    )

    assert delivery.payment_id == pending_payment.pk


@pytest.mark.django_db
def test_process__amount_mismatch_refuses_settlement(
    pending_payment: Payment,
) -> None:
    delivery = _deliver(
        "ev-short-1",
        payment_reference=pending_payment.reference,
        amount="100.00",
        currency="GBP",
    )

    pending_payment.refresh_from_db()
    assert pending_payment.status == PaymentStatus.PENDING.value
    assert "amount_mismatch" in delivery.processing_error
    assert delivery.processed_at is not None


@pytest.mark.django_db
def test_process__currency_mismatch_refuses_settlement(
    pending_payment: Payment,
) -> None:
    delivery = _deliver(
        "ev-eur-1",
        payment_reference=pending_payment.reference,
        amount="420.00",
        currency="EUR",
    )

    pending_payment.refresh_from_db()
    assert pending_payment.status == PaymentStatus.PENDING.value
    assert "amount_mismatch" in delivery.processing_error


@pytest.mark.django_db
def test_process__duplicate_succeeded_event_is_idempotent_noop(
    pending_payment: Payment,
) -> None:
    """A second settle event (fresh event_id) against an already-SUCCEEDED
    payment is a clean no-op — no error, no second signal cascade."""
    _deliver(
        "ev-dup-1",
        payment_reference=pending_payment.reference,
        amount="420.00",
        currency="GBP",
    )
    pending_payment.refresh_from_db()
    booking_status_after_first = pending_payment.booking.status

    delivery = _deliver(
        "ev-dup-2",
        payment_reference=pending_payment.reference,
        amount="420.00",
        currency="GBP",
    )

    pending_payment.refresh_from_db()
    assert pending_payment.status == PaymentStatus.SUCCEEDED.value
    assert delivery.processing_error == ""
    assert delivery.processed_at is not None
    pending_payment.booking.refresh_from_db()
    assert pending_payment.booking.status == booking_status_after_first
    # No second PaymentEvent for the duplicate settle.
    assert pending_payment.payment_events.filter(to_status="succeeded").count() == 1


@pytest.mark.django_db
def test_process__failed_after_succeeded_records_error_not_transition(
    pending_payment: Payment,
) -> None:
    _deliver(
        "ev-ooo-1",
        payment_reference=pending_payment.reference,
        amount="420.00",
        currency="GBP",
    )

    delivery = _deliver(
        "ev-ooo-2",
        event_type="failed",
        payment_reference=pending_payment.reference,
    )

    pending_payment.refresh_from_db()
    assert pending_payment.status == PaymentStatus.SUCCEEDED.value
    assert "out_of_order" in delivery.processing_error


# ----------------------------------------------------------------------
# View-level — event-id squatting and replay semantics.
# ----------------------------------------------------------------------

_WEBHOOK_URL = "/api/v1/webhooks/payments/flywire/"


def _post(client: Any, body: bytes, *, event_id: str, signature: str) -> Any:
    return client.post(
        _WEBHOOK_URL,
        data=body,
        content_type="application/json",
        HTTP_X_WEBHOOK_EVENT_ID=event_id,
        HTTP_X_WEBHOOK_SIGNATURE=signature,
    )


@pytest.mark.django_db
def test_view__unsigned_garbage_then_genuine_delivery_processes(
    client: Any, pending_payment: Payment
) -> None:
    """An attacker squatting an event_id with a garbage unsigned POST must not
    block the genuine signed delivery that arrives later."""
    garbage = b'{"event_type": "paid", "amount": "0.01"}'
    response = _post(client, garbage, event_id="ev-squat-1", signature="forged")
    assert response.status_code == 401
    delivery = WebhookDelivery.objects.get(provider="flywire", event_id="ev-squat-1")
    assert delivery.signature_valid is False

    genuine = json.dumps(
        {
            "event_id": "ev-squat-1",
            "event_type": "paid",
            "payment_reference": pending_payment.reference,
            "amount": "420.00",
            "currency": "GBP",
        }
    ).encode("utf-8")
    response = _post(client, genuine, event_id="ev-squat-1", signature=_sign(genuine))

    assert response.status_code == 200
    pending_payment.refresh_from_db()
    assert pending_payment.status == PaymentStatus.SUCCEEDED.value
    delivery.refresh_from_db()
    assert delivery.signature_valid is True
    assert pending_payment.reference in delivery.raw_body
    assert WebhookDelivery.objects.filter(event_id="ev-squat-1").count() == 1


@pytest.mark.django_db
def test_view__replay_of_signature_valid_delivery_short_circuits(
    client: Any, pending_payment: Payment
) -> None:
    body = json.dumps(
        {
            "event_id": "ev-replay-1",
            "event_type": "paid",
            "payment_reference": pending_payment.reference,
            "amount": "420.00",
            "currency": "GBP",
        }
    ).encode("utf-8")
    first = _post(client, body, event_id="ev-replay-1", signature=_sign(body))
    assert first.status_code == 200

    second = _post(client, body, event_id="ev-replay-1", signature=_sign(body))

    assert second.status_code == 200
    assert second.json()["replay"] is True
    pending_payment.refresh_from_db()
    assert pending_payment.status == PaymentStatus.SUCCEEDED.value
    assert pending_payment.payment_events.filter(to_status="succeeded").count() == 1


@pytest.mark.django_db
def test_view__still_invalid_signature_on_squatted_row_returns_401(
    client: Any, pending_payment: Payment
) -> None:
    garbage = b'{"event_type": "paid"}'
    _post(client, garbage, event_id="ev-squat-2", signature="forged")

    response = _post(client, garbage, event_id="ev-squat-2", signature="still-forged")

    assert response.status_code == 401
    delivery = WebhookDelivery.objects.get(event_id="ev-squat-2")
    assert delivery.signature_valid is False
    assert delivery.processed_at is None


# ----------------------------------------------------------------------
# Retry policy — transient errors propagate (Celery retries); permanent
# ones are recorded; the sweeper requeues rows that never processed.
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_process__unexpected_exception_propagates_and_leaves_unprocessed(
    pending_payment: Payment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient failure (DB hiccup mid-apply) must NOT be stamped as
    processed — it has to stay retryable."""
    body = json.dumps(
        {
            "event_id": "ev-transient-1",
            "event_type": "paid",
            "payment_reference": pending_payment.reference,
            "amount": "420.00",
            "currency": "GBP",
        }
    ).encode("utf-8")
    delivery, _ = WebhookDispatcher.persist(
        provider="flywire",
        event_id="ev-transient-1",
        raw_body=body,
        headers={},
        signature=_sign(body),
    )
    monkeypatch.setattr(
        WebhookDispatcher,
        "_apply",
        classmethod(lambda cls, *a, **kw: (_ for _ in ()).throw(RuntimeError("db hiccup"))),
    )

    with pytest.raises(RuntimeError):
        WebhookDispatcher.process(delivery)

    delivery.refresh_from_db()
    assert delivery.processed_at is None


@pytest.mark.django_db
def test_process__parse_error_is_permanent(db: None) -> None:
    delivery, _ = WebhookDispatcher.persist(
        provider="flywire",
        event_id="ev-garbage-1",
        raw_body=b"this is not json",
        headers={},
        signature="irrelevant",
    )

    WebhookDispatcher.process(delivery)

    delivery.refresh_from_db()
    assert delivery.processed_at is not None
    assert delivery.processing_error != ""


@pytest.mark.django_db
def test_sweep_unprocessed_webhook_deliveries_requeues_stale_rows(
    pending_payment: Payment,
) -> None:
    from datetime import timedelta

    from django.utils import timezone

    from payments.tasks import sweep_unprocessed_webhook_deliveries

    body = json.dumps(
        {
            "event_id": "ev-stale-1",
            "event_type": "paid",
            "payment_reference": pending_payment.reference,
            "amount": "420.00",
            "currency": "GBP",
        }
    ).encode("utf-8")
    stale, _ = WebhookDispatcher.persist(
        provider="flywire",
        event_id="ev-stale-1",
        raw_body=body,
        headers={},
        signature=_sign(body),
    )
    stale.signature_valid = True
    stale.save(update_fields=["signature_valid"])
    WebhookDelivery.objects.filter(pk=stale.pk).update(
        received_at=timezone.now() - timedelta(minutes=20)
    )

    fresh, _ = WebhookDispatcher.persist(
        provider="flywire",
        event_id="ev-fresh-1",
        raw_body=body,
        headers={},
        signature=_sign(body),
    )
    fresh.signature_valid = True
    fresh.save(update_fields=["signature_valid"])

    unsigned, _ = WebhookDispatcher.persist(
        provider="flywire",
        event_id="ev-unsigned-1",
        raw_body=b"garbage",
        headers={},
        signature="bad",
    )
    WebhookDelivery.objects.filter(pk=unsigned.pk).update(
        received_at=timezone.now() - timedelta(minutes=20)
    )

    requeued = sweep_unprocessed_webhook_deliveries()

    assert requeued == 1
    stale.refresh_from_db()
    assert stale.processed_at is not None  # eager Celery processed it inline
    pending_payment.refresh_from_db()
    assert pending_payment.status == PaymentStatus.SUCCEEDED.value
    fresh.refresh_from_db()
    assert fresh.processed_at is None
    unsigned.refresh_from_db()
    assert unsigned.processed_at is None
