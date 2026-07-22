"""Tests for the `zoho_backfill` management command (GAP-081 Unit 4).

The backfill replays existing rows through the SAME production push pipeline
(`ensure_pending_record` + a synchronous `push_sync_record` call per row),
wrapped in a `SyncRun(triggered_by=MANUAL)`. Suppression does NOT apply — the
backfill is the deliberate replay path.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from io import StringIO
from typing import Any, cast
from unittest import mock

import httpx
import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone

from accounts.factories import PersonFactory
from accounts.models import Person
from integrations import tasks
from integrations.enums import RunTriggeredBy, SyncProvider, SyncRunStatus, SyncStatus
from integrations.models import SyncRecord, SyncRun
from reservations.enums import EnquiryEventKind, QuotationStatus
from reservations.factories import EnquiryFactory, TermsVersionFactory
from reservations.models import Enquiry, EnquiryEvent, Quotation, TermsVersion

CONTACT_URL = "https://flow.zoho.example/contact"
ENQUIRY_URL = "https://flow.zoho.example/enquiry"
QUOTE_URL = "https://flow.zoho.example/quote"
ALL_WEBHOOKS = {
    "contact": CONTACT_URL,
    "enquiry": ENQUIRY_URL,
    "quote": QUOTE_URL,
    "booking": "",
}

pytestmark = pytest.mark.django_db


def _person(**kwargs: Any) -> Person:
    return cast(Person, PersonFactory(**kwargs))


def _enquiry(**kwargs: Any) -> Enquiry:
    return cast(Enquiry, EnquiryFactory(**kwargs))


def _quotation(
    *,
    status: str = QuotationStatus.SENT.value,
    legacy_id: str | None = None,
) -> Quotation:
    enquiry = _enquiry()
    assert enquiry.person is not None
    terms = cast(TermsVersion, TermsVersionFactory(version=f"bf-{uuid.uuid4().hex[:12]}"))
    return Quotation.objects.create(
        enquiry=enquiry,
        person=enquiry.person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
        status=status,
        legacy_id=legacy_id,
    )


@pytest.fixture
def post_mock(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """Record every webhook POST; respond 200."""

    def _ok(url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, request=httpx.Request("POST", url))

    m = mock.Mock(side_effect=_ok)
    monkeypatch.setattr(tasks.httpx, "post", m)
    return m


def _run(*args: str, **kwargs: Any) -> str:
    out = StringIO()
    call_command("zoho_backfill", *args, per_minute=100_000, stdout=out, **kwargs)
    return out.getvalue()


def _posted_urls(post_mock: mock.Mock) -> list[str]:
    return [call.args[0] for call in post_mock.call_args_list]


def test_pushes_kinds_in_dependency_order_and_records_sync_run(post_mock: mock.Mock) -> None:
    _person()
    _enquiry()  # brings its own person
    _quotation()  # brings its own enquiry + person

    with override_settings(ZOHO_FLOW_WEBHOOKS=ALL_WEBHOOKS):
        _run()

    urls = _posted_urls(post_mock)
    assert urls.count(CONTACT_URL) == 3
    assert urls.count(ENQUIRY_URL) == 2
    assert urls.count(QUOTE_URL) == 1
    # Dependency order: every contact before every enquiry before every quote.
    assert max(i for i, u in enumerate(urls) if u == CONTACT_URL) < min(
        i for i, u in enumerate(urls) if u == ENQUIRY_URL
    )
    assert max(i for i, u in enumerate(urls) if u == ENQUIRY_URL) < min(
        i for i, u in enumerate(urls) if u == QUOTE_URL
    )

    run = SyncRun.objects.get()
    assert run.provider == SyncProvider.ZOHO_CRM
    assert run.triggered_by == RunTriggeredBy.MANUAL
    assert run.status == SyncRunStatus.SUCCEEDED
    assert run.records_processed == 6
    assert run.records_succeeded == 6
    assert run.records_failed == 0
    assert run.error_summary == ""
    assert run.finished_at is not None

    assert not SyncRecord.objects.exclude(status=SyncStatus.IN_SYNC.value).exists()
    assert SyncRecord.objects.count() == 6


def test_failure_marks_run_partial_with_error_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good = _person()
    bad = _person()

    def _selective(url: str, **kwargs: Any) -> httpx.Response:
        status = 422 if kwargs["json"]["RES_ID"] == bad.pk else 200
        return httpx.Response(status, request=httpx.Request("POST", url))

    monkeypatch.setattr(tasks.httpx, "post", mock.Mock(side_effect=_selective))

    with override_settings(ZOHO_FLOW_WEBHOOKS=ALL_WEBHOOKS):
        _run()

    run = SyncRun.objects.get()
    assert run.status == SyncRunStatus.PARTIAL
    assert run.records_processed == 2
    assert run.records_succeeded == 1
    assert run.records_failed == 1
    assert "422" in run.error_summary
    assert f"#{bad.pk}" in run.error_summary

    assert SyncRecord.objects.get(object_id=bad.pk).status == SyncStatus.ERROR
    assert SyncRecord.objects.get(object_id=good.pk).status == SyncStatus.IN_SYNC


def test_all_failures_mark_run_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    _person()

    def _reject(url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(422, request=httpx.Request("POST", url))

    monkeypatch.setattr(tasks.httpx, "post", mock.Mock(side_effect=_reject))

    with override_settings(ZOHO_FLOW_WEBHOOKS=ALL_WEBHOOKS):
        _run()

    run = SyncRun.objects.get()
    assert run.status == SyncRunStatus.FAILED
    assert run.records_succeeded == 0
    assert run.records_failed == 1


def test_skips_anonymized_draft_and_synthetic(post_mock: mock.Mock) -> None:
    erased = _person()
    erased.anonymize()
    _quotation(status=QuotationStatus.DRAFT.value)
    _quotation(legacy_id="booking-77")  # synthetic fill row, SENT

    with override_settings(ZOHO_FLOW_WEBHOOKS=ALL_WEBHOOKS):
        _run()

    urls = _posted_urls(post_mock)
    assert QUOTE_URL not in urls  # both quotations excluded
    pushed_res_ids = [call.kwargs["json"]["RES_ID"] for call in post_mock.call_args_list]
    contact_ids = [
        call.kwargs["json"]["RES_ID"]
        for call in post_mock.call_args_list
        if call.args[0] == CONTACT_URL
    ]
    assert erased.pk not in contact_ids
    assert pushed_res_ids  # the factories' other rows did push


def _mark_sent(quotation: Quotation) -> None:
    """Write the QUOTE_SENT send marker `record_quote_sent` leaves behind."""
    EnquiryEvent.objects.create(
        enquiry=quotation.enquiry,
        from_status=quotation.enquiry.status,
        to_status=quotation.enquiry.status,
        kind=EnquiryEventKind.QUOTE_SENT.value,
        meta={"quotation_id": quotation.pk, "send_path": "smtp"},
    )


def test_quote_eligibility_requires_an_actual_send(post_mock: mock.Mock) -> None:
    """A never-sent quote stays out of the CRM regardless of status: DRAFTs
    age to EXPIRED via the beat and can be CANCELLED — without a QUOTE_SENT
    send marker those never reached a customer. Legacy-loaded quotations are
    stamped DRAFT by the loader (no send markers), so a legacy row aged
    EXPIRED by the beat stays excluded too."""
    sent = _quotation(status=QuotationStatus.SENT.value)
    accepted = _quotation(status=QuotationStatus.ACCEPTED.value)
    sent_then_expired = _quotation(status=QuotationStatus.EXPIRED.value)
    _mark_sent(sent_then_expired)
    sent_then_cancelled = _quotation(status=QuotationStatus.CANCELLED.value)
    _mark_sent(sent_then_cancelled)
    _quotation(status=QuotationStatus.EXPIRED.value)  # aged draft, never sent
    _quotation(status=QuotationStatus.CANCELLED.value)  # culled draft, never sent
    _quotation(status=QuotationStatus.EXPIRED.value, legacy_id="4711")  # legacy, aged

    with override_settings(ZOHO_FLOW_WEBHOOKS=ALL_WEBHOOKS):
        _run("--kinds", "quote")

    pushed = {call.kwargs["json"]["RES_ID"] for call in post_mock.call_args_list}
    assert pushed == {sent.pk, accepted.pk, sent_then_expired.pk, sent_then_cancelled.pk}


def test_crash_mid_run_still_finalizes_sync_run(
    post_mock: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unexpected crash (or SIGINT) must not leave the SyncRun dangling
    RUNNING with zeroed counters — the finally block closes it with whatever
    accumulated (some successes → PARTIAL)."""
    _person()
    _person()
    sleep = mock.Mock(side_effect=[RuntimeError("interrupted")])
    monkeypatch.setattr("integrations.management.commands.zoho_backfill.time.sleep", sleep)

    with override_settings(ZOHO_FLOW_WEBHOOKS=ALL_WEBHOOKS), pytest.raises(RuntimeError):
        call_command("zoho_backfill", per_minute=30, stdout=StringIO())

    run = SyncRun.objects.get()
    assert run.status == SyncRunStatus.PARTIAL  # 1 success before the crash
    assert run.records_processed == 1
    assert run.records_succeeded == 1
    assert run.records_failed == 0
    assert run.finished_at is not None


def test_transport_error_is_single_attempt_and_leaves_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canary for the direct-call retry semantics: when the delivery task is
    called synchronously (`called_directly`), Celery's autoretry must NOT loop
    — one POST attempt, row counted failed, record left PENDING with
    retry_count bumped, run completes. If a Celery upgrade changes the
    called-directly behaviour, this test catches it."""
    good = _person()
    bad = _person()

    def _selective(url: str, **kwargs: Any) -> httpx.Response:
        if kwargs["json"]["RES_ID"] == bad.pk:
            raise httpx.ConnectError("network down")
        return httpx.Response(200, request=httpx.Request("POST", url))

    post = mock.Mock(side_effect=_selective)
    monkeypatch.setattr(tasks.httpx, "post", post)

    with override_settings(ZOHO_FLOW_WEBHOOKS=ALL_WEBHOOKS):
        _run()

    bad_attempts = [c for c in post.call_args_list if c.kwargs["json"]["RES_ID"] == bad.pk]
    assert len(bad_attempts) == 1

    run = SyncRun.objects.get()
    assert run.status == SyncRunStatus.PARTIAL
    assert run.records_succeeded == 1
    assert run.records_failed == 1
    assert "ConnectError" in run.error_summary

    bad_record = SyncRecord.objects.get(object_id=bad.pk)
    assert bad_record.status == SyncStatus.PENDING
    assert bad_record.retry_count == 1
    assert SyncRecord.objects.get(object_id=good.pk).status == SyncStatus.IN_SYNC


def test_kinds_filter_respected(post_mock: mock.Mock) -> None:
    _person()
    _enquiry()

    with override_settings(ZOHO_FLOW_WEBHOOKS=ALL_WEBHOOKS):
        _run("--kinds", "contact")

    urls = _posted_urls(post_mock)
    assert set(urls) == {CONTACT_URL}


def test_invalid_kind_rejected() -> None:
    with pytest.raises(CommandError):
        _run("--kinds", "contact,villa")


def test_unset_url_skips_kind_with_message(post_mock: mock.Mock) -> None:
    _person()
    _enquiry()

    with override_settings(
        ZOHO_FLOW_WEBHOOKS={**ALL_WEBHOOKS, "enquiry": ""},
    ):
        out = _run()

    assert "enquiry" in out
    assert "skip" in out.lower()
    urls = _posted_urls(post_mock)
    assert ENQUIRY_URL not in urls
    assert CONTACT_URL in urls
    run = SyncRun.objects.get()
    assert run.records_failed == 0
    assert run.status == SyncRunStatus.SUCCEEDED


def test_second_run_is_idempotent(post_mock: mock.Mock) -> None:
    _person()
    _enquiry()

    with override_settings(ZOHO_FLOW_WEBHOOKS=ALL_WEBHOOKS):
        _run()
        first_count = SyncRecord.objects.count()
        _run()

    assert SyncRecord.objects.count() == first_count
    assert not SyncRecord.objects.exclude(status=SyncStatus.IN_SYNC.value).exists()
    assert SyncRun.objects.count() == 2
    second = SyncRun.objects.order_by("started_at").last()
    assert second is not None
    assert second.status == SyncRunStatus.SUCCEEDED


def test_throttle_sleeps_between_pushes(
    post_mock: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _person()
    _person()
    sleep = mock.Mock()
    monkeypatch.setattr("integrations.management.commands.zoho_backfill.time.sleep", sleep)

    out = StringIO()
    with override_settings(ZOHO_FLOW_WEBHOOKS=ALL_WEBHOOKS):
        call_command("zoho_backfill", per_minute=30, stdout=out)

    assert sleep.call_count == 2
    assert sleep.call_args_list[0].args == (2.0,)
