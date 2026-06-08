"""Celery task skeletons for the integrations app.

These are decorated as Celery tasks but their bodies are not yet implemented
(they raise ``NotImplementedError``). They are deliberately **not** registered
in ``CELERY_BEAT_SCHEDULE`` until implemented — otherwise beat would raise on
every tick. Wire each into the schedule as part of its own implementation
ticket.
"""

from __future__ import annotations

from celery import shared_task


@shared_task
def push_pending() -> None:
    """Batch-push `SyncRecord`s in `PENDING` state to their providers.

    Runs every few minutes via Celery beat. Idempotent — re-running on the
    same PENDING row just retries the push.
    """
    raise NotImplementedError("push_pending is wired in v1.1")


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
