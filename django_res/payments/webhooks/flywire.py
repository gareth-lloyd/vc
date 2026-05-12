"""Flywire-specific webhook parser.

Flywire posts a JSON body keyed by `event_id`, `event_type`,
`payment_reference`, `provider_reference`, `amount`, `currency`,
`settled_at`. The legacy app hardcoded a `VC` prefix in the body parser;
the new flow routes on `<provider_slug>` in the URL and treats the body
as opaque JSON.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from django.utils.dateparse import parse_datetime

from payments.models.webhook_delivery import WebhookDelivery
from payments.webhooks.base import ProviderEvent

# Map Flywire's status tokens to our internal event kinds. The internal
# kinds align with `WebhookDispatcher._apply`'s status map.
_FLYWIRE_STATUS_MAP: dict[str, str] = {
    "paid": "succeeded",
    "settled": "succeeded",
    "completed": "succeeded",
    "failed": "failed",
    "declined": "failed",
    "refunded": "refunded",
    "cancelled": "cancelled",
}


def parse_flywire_event(delivery: WebhookDelivery) -> ProviderEvent:
    """Translate a Flywire webhook body into a `ProviderEvent`."""
    try:
        body = json.loads(delivery.raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Flywire webhook body is not valid JSON: {exc}") from exc

    raw_status = str(body.get("event_type") or body.get("status") or "").lower()
    event_kind = _FLYWIRE_STATUS_MAP.get(raw_status, raw_status or "unknown")

    amount_raw = body.get("amount")
    amount = Decimal(str(amount_raw)) if amount_raw is not None else None

    settled_raw = body.get("settled_at") or body.get("processed_at")
    settled_at: datetime | None = None
    if settled_raw:
        try:
            settled_at = parse_datetime(settled_raw)
        except (TypeError, ValueError):
            settled_at = None

    return ProviderEvent(
        event_kind=event_kind,
        payment_reference=str(body.get("payment_reference") or ""),
        provider_reference=str(body.get("provider_reference") or body.get("id") or ""),
        amount=amount,
        currency_code=str(body.get("currency") or ""),
        settled_at=settled_at,
        raw=body,
    )
