"""`zoho_backfill` — replay existing rows to Zoho Flow (GAP-081 Unit 4).

Pushes every eligible row of each registered kind through the SAME production
pipeline as live traffic — `ensure_pending_record` + a synchronous
`push_sync_record` call — so `SyncRecord` state updates identically. This is
the deliberate, throttled replay path for loaded legacy data (loader-time
pushes are suppressed in `data_migration.BaseLoader`); idempotent by
construction (PENDING upsert + upsert semantics in the Flow keyed on RES_ID).

Kinds run in dependency order contact → enquiry → quote so nested RES_ID
references land after their targets. A kind with an unset webhook URL is
skipped with a message (never counted as failures). The whole run is wrapped
in a `SyncRun(triggered_by=MANUAL)` with counters + `error_summary` — no
`SyncIssue` writes (that model stays for the unbuilt reconcile path).
"""

from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import models
from django.utils import timezone

from integrations.enums import (
    RunTriggeredBy,
    SyncDirection,
    SyncProvider,
    SyncRunStatus,
    SyncStatus,
)
from integrations.models import SyncRun
from integrations.services.zoho_flow import (
    ensure_pending_record,
    registered_zoho_models,
    webhook_url,
)
from integrations.tasks import push_sync_record

# Dependency order: contacts first (enquiries/quotes nest person RES_IDs),
# then enquiries (quotes nest enquiry RES_IDs), then quotes. `booking` is
# reserved but dormant (no endpoint until the ~Sept booking build).
KIND_ORDER = ("contact", "enquiry", "quote")

ERROR_SUMMARY_MAX_LINES = 50


class Command(BaseCommand):
    help = (
        "Replay existing records to the Zoho Flow webhooks through the "
        "production push pipeline, kind by kind (contact → enquiry → quote)."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--kinds",
            default=",".join(KIND_ORDER),
            help=f"Comma-separated subset of {'/'.join(KIND_ORDER)} (default: all).",
        )
        parser.add_argument(
            "--per-minute",
            type=int,
            default=60,
            help="Throttle: max pushes per minute (default 60).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        kinds = [k.strip() for k in options["kinds"].split(",") if k.strip()]
        invalid = sorted(set(kinds) - set(KIND_ORDER))
        if invalid:
            raise CommandError(
                f"Unknown kind(s) {', '.join(invalid)}; expected a subset of {KIND_ORDER}"
            )
        per_minute = options["per_minute"]
        if per_minute < 1:
            raise CommandError("--per-minute must be >= 1")
        delay = 60.0 / per_minute

        models_by_kind = {spec.kind: model for model, spec in registered_zoho_models().items()}

        run = SyncRun.objects.create(
            provider=SyncProvider.ZOHO_CRM.value,
            direction=SyncDirection.PUSH.value,
            started_at=timezone.now(),
            triggered_by=RunTriggeredBy.MANUAL.value,
        )
        processed = succeeded = failed = 0
        errors: list[str] = []
        completed = False

        # try/finally: a crash or SIGINT mid-run must not leave the SyncRun
        # dangling RUNNING with zeroed counters — close it with whatever
        # accumulated (the exception still propagates).
        try:
            for kind in (k for k in KIND_ORDER if k in kinds):
                if not webhook_url(kind):
                    self.stdout.write(f"[{kind}] webhook URL unset — kind skipped")
                    continue
                model = models_by_kind.get(kind)
                if model is None:
                    self.stdout.write(f"[{kind}] no registered model — kind skipped")
                    continue

                kind_ok = kind_failed = 0
                for instance in self._queryset_for(kind, model).iterator():
                    record = ensure_pending_record(instance)
                    error = self._push(record.pk)
                    processed += 1
                    if error is None:
                        kind_ok += 1
                        succeeded += 1
                    else:
                        kind_failed += 1
                        failed += 1
                        if len(errors) < ERROR_SUMMARY_MAX_LINES:
                            errors.append(f"{kind} #{instance.pk}: {error}"[:300])
                    time.sleep(delay)
                self.stdout.write(f"[{kind}] {kind_ok} pushed, {kind_failed} failed")
            completed = True
        finally:
            run.finished_at = timezone.now()
            run.records_processed = processed
            run.records_succeeded = succeeded
            run.records_failed = failed
            run.error_summary = "\n".join(errors)
            if not completed:
                # Interrupted: PARTIAL when anything landed, else FAILED.
                run.status = (
                    SyncRunStatus.PARTIAL.value if succeeded else SyncRunStatus.FAILED.value
                )
            elif failed == 0:
                run.status = SyncRunStatus.SUCCEEDED.value
            elif succeeded > 0:
                run.status = SyncRunStatus.PARTIAL.value
            else:
                run.status = SyncRunStatus.FAILED.value
            run.save(
                update_fields=[
                    "finished_at",
                    "records_processed",
                    "records_succeeded",
                    "records_failed",
                    "error_summary",
                    "status",
                    "updated_at",
                ]
            )
            self.stdout.write(
                f"SyncRun #{run.pk} {run.status}: "
                f"{processed} processed, {succeeded} succeeded, {failed} failed"
            )

    def _queryset_for(self, kind: str, model: type[models.Model]) -> models.QuerySet[Any]:
        """Eligible rows per kind.

        contact: skip ANONYMIZED (never pushed — enqueue and delivery both
        guard too).

        quote: `.real()` only (`booking-` synthetic fill rows on the
        Quotation itself, `reservations/models/quotation.py`), and only
        quotes a customer actually received — a never-sent quote stays out
        of the CRM regardless of status (drafts-never-push principle; there
        is no CRM delete endpoint to undo a mistake). SENT/ACCEPTED are
        sent by definition; EXPIRED/CANCELLED are reachable straight from
        DRAFT (`Quotation.expire()` beat / `cancel()`), so those count only
        when a QUOTE_SENT send marker exists (`EnquiryEvent` with
        `meta.quotation_id`, written by `record_quote_sent` on every send
        path). Legacy provenance does NOT widen the rule: `QuotationLoader`
        stamps every legacy quotation DRAFT (`data_migration/loaders/
        finance.py`, `status: QuotationStatus.DRAFT`) and no loader writes
        EnquiryEvents — legacy quotes are deliberately excluded from the
        backfill (plan decision 9), including after the beat ages them
        DRAFT→EXPIRED.

        Status/kind literals are duck-typed strings and the reservations
        models are resolved via `apps.get_model`: the import spine forbids
        integrations → reservations, and these values are frozen TextChoices
        pinned by the reservations test suite.
        """
        manager = model._default_manager
        if kind == "contact":
            from accounts.enums import PersonStatus

            return manager.exclude(status=PersonStatus.ANONYMIZED).order_by("pk")
        if kind == "quote":
            from django.apps import apps
            from django.db.models.functions import Cast

            event_model = apps.get_model("reservations", "EnquiryEvent")
            # meta->quotation_id is jsonb; Postgres has no bigint=jsonb
            # operator, so cast the outer pk bigint→text→jsonb (a JSON
            # number literal) for the comparison.
            outer_pk_as_json = Cast(
                Cast(models.OuterRef("pk"), models.TextField()), models.JSONField()
            )
            sent_marker = event_model._default_manager.filter(
                kind="quote_sent",
                meta__quotation_id=outer_pk_as_json,
            )
            # `.real()` lives on the Quotation queryset (duck-typed — see above).
            return (
                manager.real()  # type: ignore[attr-defined]
                .filter(
                    models.Q(status__in=("sent", "accepted"))
                    | (
                        models.Q(status__in=("expired", "cancelled"))
                        & models.Q(models.Exists(sent_marker))
                    )
                )
                .order_by("pk")
            )
        return manager.all().order_by("pk")

    def _push(self, record_pk: int) -> str | None:
        """Push one record synchronously through the production delivery task.

        Calling the task function directly (not `.delay`) reuses the exact
        delivery logic — payload built at push time, 2xx/4xx/5xx handling,
        SyncRecord state writes. Returns None on success, else a short error
        string. A raise here is a transport/5xx failure (the direct call
        re-raises instead of autoretrying); a 4xx parks the record ERROR
        without raising, so the record status is re-read to classify.
        """
        from integrations.models import SyncRecord

        try:
            push_sync_record(record_pk)
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"[:200]
        record = SyncRecord.objects.filter(pk=record_pk).first()
        if record is None:
            return "SyncRecord vanished during push"
        if record.status == SyncStatus.IN_SYNC.value:
            return None
        return record.error_message[:200] or f"record left {record.status}"
