"""Record-or-replay wrapper around `IntegrationInboundCall`.

`produce` runs inside a transaction together with the ledger insert, so a
failure records nothing (a retry reprocesses) and a duplicate-key insert rolls
the side effects back before replaying the recorded response.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

import structlog
from django.db import IntegrityError, transaction

from integrations.models import IntegrationInboundCall

logger = structlog.get_logger(__name__)

_UNIQUE_CONSTRAINT = "unique_inbound_call_per_provider_key"


def _body_hash(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def record_or_replay(
    *,
    provider: str,
    idempotency_key: str,
    produce: Callable[[], tuple[int, dict[str, Any]]],
) -> tuple[IntegrationInboundCall, bool]:
    """Run `produce` once per (provider, idempotency_key).

    Returns `(call, replayed)`. On a repeat key, `produce` is not invoked and
    the previously recorded call row is returned with `replayed=True`.
    `produce` must return a plain-JSON body (str/int/bool/None leaves only) —
    Decimals/datetimes are the caller's job to stringify.
    """
    existing = IntegrationInboundCall.objects.filter(
        provider=provider, idempotency_key=idempotency_key
    ).first()
    if existing is not None:
        logger.info(
            "integrations.inbound_call.replayed",
            provider=provider,
            idempotency_key=idempotency_key,
        )
        return existing, True

    try:
        with transaction.atomic():
            status, body = produce()
            call = IntegrationInboundCall.objects.create(
                provider=provider,
                idempotency_key=idempotency_key,
                response_status=status,
                response_body=body,
                response_body_hash=_body_hash(body),
            )
    except IntegrityError as exc:
        # Lost a concurrent race on OUR unique key: the atomic block rolled
        # `produce`'s writes back; replay the winner's recorded response. An
        # IntegrityError from inside `produce` (some unrelated constraint)
        # must propagate — never masquerade as a replay.
        if _UNIQUE_CONSTRAINT not in str(exc):
            raise
        replay = IntegrationInboundCall.objects.filter(
            provider=provider, idempotency_key=idempotency_key
        ).first()
        if replay is None:
            raise
        logger.info(
            "integrations.inbound_call.replayed",
            provider=provider,
            idempotency_key=idempotency_key,
        )
        return replay, True
    return call, False
