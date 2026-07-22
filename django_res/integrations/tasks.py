"""Celery tasks for the integrations app.

`push_sync_record` / `push_pending` implement the Zoho Flow outbound push
(GAP-081). `reconcile_provider` / `refresh_oauth_tokens` remain skeletons —
decorated but unscheduled (beat would error on every tick), for manual
`.delay` use only once implemented.
"""

from __future__ import annotations

from datetime import timedelta

import httpx
import structlog
from celery import shared_task
from django.utils import timezone

from integrations.enums import SyncProvider, SyncStatus
from integrations.models import SyncRecord
from integrations.services.zoho_flow import (
    get_zoho_spec,
    is_anonymized_person,
    registered_zoho_models,
    webhook_url,
)

logger = structlog.get_logger(__name__)

PUSH_TIMEOUT_SECONDS = 20.0
PUSH_MAX_RETRIES = 6
# Grace before the sweep re-dispatches a PENDING row: avoids double-dispatch
# racing the on_commit task and rows mid-autoretry-backoff (max 600s).
PUSH_SWEEP_GRACE = timedelta(minutes=15)
PUSH_SWEEP_BATCH = 200


class TransientPushError(Exception):
    """A retryable delivery failure (5xx from the Flow endpoint)."""


@shared_task(
    autoretry_for=(httpx.TransportError, TransientPushError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=PUSH_MAX_RETRIES,
)
def push_sync_record(sync_record_id: int) -> None:
    """POST one `SyncRecord`'s target to its kind's Zoho Flow webhook.

    Payload is built at push time from the live target row. Outcomes:
    2xx → IN_SYNC + `last_pushed_at`, error cleared, `retry_count` reset (via
    a guarded write — a concurrent PENDING bump wins); 4xx / builder error →
    permanent: ERROR + `error_message`, no retry; transport error / 5xx →
    bump `retry_count` and re-raise for autoretry (backoff+jitter, max 6);
    once `retry_count` exceeds the retry budget the row is parked ERROR so
    the sweep stops re-dispatching it. Missing record / unset URL → silent
    no-op; vanished target → record deleted; anonymized Person → DISABLED.
    """
    record = SyncRecord.objects.filter(pk=sync_record_id).first()
    if record is None:
        return
    target = record.target
    if target is None:
        # Target hard-deleted after enqueue. Backstop for anything the
        # registry's post_delete reaper missed — a SyncRecord without a
        # target is meaningless, and left PENDING it would clog the sweep's
        # per-tick cap forever.
        record.delete()
        return
    spec = get_zoho_spec(target._meta.model)
    if spec is None:
        return
    url = webhook_url(spec.kind)
    if not url:
        return
    if is_anonymized_person(target):
        # Anonymized between enqueue and delivery: never push, but keep the
        # row as the ops trail — DISABLED drops it out of the PENDING sweep.
        record.status = SyncStatus.DISABLED.value
        record.save(update_fields=["status", "updated_at"])
        return

    try:
        payload = spec.build_payload(target)
    except Exception as exc:
        # A broken builder is a poison pill: raising leaves the row PENDING
        # and the sweep re-dispatches it every tick. Park it ERROR (class +
        # message only — never payload contents).
        record.status = SyncStatus.ERROR.value
        record.error_message = f"{type(exc).__name__}: {exc}"[:500]
        record.save(update_fields=["status", "error_message", "updated_at"])
        logger.warning(
            "integrations.zoho_push_payload_failed",
            sync_record_id=record.pk,
            kind=spec.kind,
            error_class=type(exc).__name__,
        )
        return

    try:
        response = httpx.post(url, json=payload, timeout=PUSH_TIMEOUT_SECONDS)
    except httpx.TransportError as exc:
        if _record_transient_failure(record, repr(exc)):
            return  # retry budget spent — parked ERROR, stop raising
        raise

    if response.is_success:
        # Guarded write: only stamp IN_SYNC if the row is untouched since this
        # task read it. A concurrent edit's PENDING bump (whose own dispatch
        # may have been lost) must win — the sweep only repairs PENDING rows,
        # so blindly overwriting could strand that edit unsynced forever.
        now = timezone.now()
        matched = SyncRecord.objects.filter(pk=record.pk, updated_at=record.updated_at).update(
            status=SyncStatus.IN_SYNC.value,
            last_pushed_at=now,
            error_message="",
            retry_count=0,
            updated_at=now,
        )
        if not matched:
            logger.info("integrations.zoho_push_superseded", sync_record_id=record.pk)
        return

    detail = f"HTTP {response.status_code}: {response.text[:500]}"
    if response.status_code < 500:
        # Permanent: the payload/endpoint is wrong — retrying can't fix it.
        record.status = SyncStatus.ERROR.value
        record.error_message = detail
        record.save(update_fields=["status", "error_message", "updated_at"])
        logger.warning(
            "integrations.zoho_push_rejected",
            sync_record_id=record.pk,
            kind=spec.kind,
            status_code=response.status_code,
        )
        return

    if _record_transient_failure(record, detail):
        return  # retry budget spent — parked ERROR, stop raising
    raise TransientPushError(detail)


def _record_transient_failure(record: SyncRecord, detail: str) -> bool:
    """Bump `retry_count`; park the row ERROR once the retry budget is spent.

    Returns True when exhausted (caller must NOT re-raise: parking instead of
    raising forever stops the beat sweep re-dispatching a row whose autoretry
    chain already burned its budget — the ERROR row is the ops signal, as with
    exhausted comms/payments rows). Returns False while budget remains, so
    the caller re-raises for autoretry.
    """
    record.retry_count += 1
    record.error_message = detail
    if record.retry_count > PUSH_MAX_RETRIES:
        record.status = SyncStatus.ERROR.value
        record.save(update_fields=["status", "retry_count", "error_message", "updated_at"])
        logger.warning(
            "integrations.zoho_push_exhausted",
            sync_record_id=record.pk,
            retry_count=record.retry_count,
        )
        return True
    record.save(update_fields=["retry_count", "error_message", "updated_at"])
    return False


@shared_task
def push_pending() -> int:
    """Beat sweep: re-dispatch PENDING Zoho Flow rows the broker lost.

    Backstop for enqueues lost between commit and broker publish (Redis is
    not durable) and for rows whose retry chain died with the worker. Only
    rows whose target model is registered with a *configured* webhook URL,
    older than the grace window, oldest first, capped per tick. Returns the
    number dispatched.
    """
    from django.contrib.contenttypes.models import ContentType

    content_types = [
        ContentType.objects.get_for_model(model)
        for model, spec in registered_zoho_models().items()
        if webhook_url(spec.kind)
    ]
    if not content_types:
        return 0
    cutoff = timezone.now() - PUSH_SWEEP_GRACE
    pending_ids = list(
        SyncRecord.objects.filter(
            provider=SyncProvider.ZOHO_CRM.value,
            status=SyncStatus.PENDING.value,
            content_type__in=content_types,
            updated_at__lt=cutoff,
        )
        .order_by("updated_at")
        .values_list("pk", flat=True)[:PUSH_SWEEP_BATCH]
    )
    for record_id in pending_ids:
        push_sync_record.delay(record_id)
    if pending_ids:
        logger.info("integrations.zoho_push_sweep", dispatched=len(pending_ids))
    return len(pending_ids)


@shared_task
def reconcile_provider(provider: str) -> None:
    """Nightly drift reconciliation for `provider`.

    Opens a `SyncRun`, walks every `SyncRecord` for the provider with
    `status != DISABLED`, compares remote vs local fingerprint, writes
    `SyncIssue` rows for drift/missing/transient failures, and closes the
    run with SUCCEEDED/PARTIAL/FAILED.
    """
    raise NotImplementedError("reconcile_provider is wired in v1.1")


@shared_task
def refresh_oauth_tokens() -> None:
    """Hourly pre-emptive refresh of `OAuthCredential` rows near expiry.

    Looks up active credentials whose `expires_at` is within the next hour
    and refreshes them via `OAuthService` so the synchronous-refresh path
    in `get_access_token` is rarely exercised in production.
    """
    raise NotImplementedError("refresh_oauth_tokens is wired in v1.1")
