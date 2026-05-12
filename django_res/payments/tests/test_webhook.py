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
