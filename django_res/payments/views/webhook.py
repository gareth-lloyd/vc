"""Public HTTP entry points for the payments app.

Today this is just the webhook ingestion view; richer
deposit/balance/refund REST endpoints land in a later iteration once the
DRF surface is fleshed out.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from payments.tasks import process_webhook_delivery
from payments.webhooks.base import WebhookDispatcher


def _event_id_from(request: HttpRequest, body: bytes) -> str:
    """Pick a provider event_id off the request.

    Each provider names its id differently — Flywire calls it
    `X-Flywire-Event-Id`, Stripe `Stripe-Signature` plus an `id` in the body.
    We accept either the header or a JSON `event_id` / `id` on the body,
    falling back to a SHA hash of the body so duplicate deliveries collide.
    """
    header = (
        request.headers.get("X-Webhook-Event-Id")
        or request.headers.get("X-Flywire-Event-Id")
        or request.headers.get("X-Stripe-Event-Id")
    )
    if header:
        return header
    try:
        import json

        parsed: Any = json.loads(body.decode("utf-8", errors="replace"))
        if isinstance(parsed, dict):
            candidate = parsed.get("event_id") or parsed.get("id")
            if candidate:
                return str(candidate)
    except Exception:
        pass
    import hashlib

    return hashlib.sha256(body).hexdigest()


@csrf_exempt
@require_POST
def webhook_view(request: HttpRequest, provider_slug: str) -> HttpResponse:
    """Persist-first webhook receiver.

    Routing happens on `<provider_slug>` (URL), not on a body prefix.
    Returns 200 immediately on persist — actual processing runs in a
    Celery task to avoid blocking the provider on our business logic.
    """
    raw_body = request.body
    signature = (
        request.headers.get("X-Webhook-Signature")
        or request.headers.get("X-Flywire-Signature")
        or request.headers.get("Stripe-Signature")
        or ""
    )
    event_id = _event_id_from(request, raw_body)
    headers = {k: v for k, v in request.headers.items()}

    delivery, created = WebhookDispatcher.persist(
        provider=provider_slug,
        event_id=event_id,
        raw_body=raw_body,
        headers=headers,
        signature=signature,
    )

    if not created:
        # Replay: short-circuit with the original outcome.
        return JsonResponse(
            {
                "delivery_id": delivery.pk,
                "replay": True,
                "processed": delivery.processed_at is not None,
            },
            status=200,
        )

    signature_valid = WebhookDispatcher.verify_signature(
        provider=provider_slug,
        raw_body=raw_body,
        signature=signature,
    )
    delivery.signature_valid = signature_valid
    delivery.save(update_fields=["signature_valid", "updated_at"])

    if not signature_valid:
        return JsonResponse(
            {"delivery_id": delivery.pk, "error": "invalid_signature"},
            status=401,
        )

    # TODO: enqueue Celery `process_webhook_delivery.delay(delivery.pk)`.
    # For now we process inline so the synchronous test suite can observe
    # the side effects; production must run this off-thread.
    process_webhook_delivery(delivery.pk)

    return JsonResponse({"delivery_id": delivery.pk, "replay": False}, status=200)
