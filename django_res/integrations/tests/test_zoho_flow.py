"""Tests for the Zoho Flow outbound push core (GAP-081).

Covers the registry (`register_zoho_flow`), the enqueue path
(`enqueue_zoho_push` + suppression + skip rules), the delivery task
(`push_sync_record`), and the beat sweep (`push_pending`).

`accounts.Person` is registered by `integrations.apps.ready()`; these tests
NEVER unregister it (xdist worker leak) — they toggle behaviour via
`override_settings(ZOHO_FLOW_WEBHOOKS=…)` instead. Sacrificial registrations
use `accounts.User` with `auto_push=False` (no signal side effects) and are
unregistered after.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any, cast
from unittest import mock

import httpx
import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.utils import timezone

from accounts.factories import PersonFactory
from accounts.models import Person, PersonEmail, PersonPhone, User
from integrations import tasks
from integrations.enums import SyncDirection, SyncProvider, SyncStatus
from integrations.models import SyncRecord
from integrations.services.zoho_flow import (
    ZohoFlowSpec,
    enqueue_zoho_push,
    get_zoho_spec,
    register_zoho_flow,
    suppress_zoho_push,
    unregister_zoho_flow,
    webhook_url,
)
from integrations.tasks import TransientPushError, push_pending, push_sync_record
from properties.models.property import Property

CONTACT_URL = "https://flow.zoho.example/contact"
WEBHOOKS = {"contact": CONTACT_URL, "enquiry": "", "quote": "", "booking": ""}


def _person(**kwargs: Any) -> Person:
    return cast(Person, PersonFactory(**kwargs))


@pytest.fixture
def contact_webhook() -> Iterator[None]:
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        yield


@pytest.fixture
def delay_mock(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    m = mock.Mock()
    monkeypatch.setattr(tasks.push_sync_record, "delay", m)
    return m


def _person_ct() -> ContentType:
    return ContentType.objects.get_for_model(Person)


def _make_record(
    object_id: int,
    *,
    content_type: ContentType | None = None,
    status: str = SyncStatus.PENDING.value,
) -> SyncRecord:
    # get_or_create: with a webhook URL configured, saving a Person has
    # already auto-created its PENDING record via the registered post_save.
    record, _ = SyncRecord.objects.get_or_create(
        content_type=content_type or _person_ct(),
        object_id=object_id,
        provider=SyncProvider.ZOHO_CRM.value,
        defaults={
            "direction": SyncDirection.PUSH.value,
            "status": status,
        },
    )
    return record


def _mark_in_sync(record: SyncRecord) -> None:
    record.status = SyncStatus.IN_SYNC.value
    record.save(update_fields=["status", "updated_at"])


# --- registry -------------------------------------------------------------


def test_register_and_lookup_spec() -> None:
    def _builder(instance: Any) -> dict[str, Any]:
        return {}

    register_zoho_flow(User, kind="contact", build_payload=_builder, auto_push=False)
    try:
        spec = get_zoho_spec(User)
        assert spec is not None
        assert spec.kind == "contact"
        assert spec.build_payload is _builder
        assert spec.auto_push is False
    finally:
        unregister_zoho_flow(User)


def test_register_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="villa"):
        register_zoho_flow(User, kind="villa", build_payload=lambda i: {}, auto_push=False)


def test_unregistered_model_has_no_spec() -> None:
    assert get_zoho_spec(Property) is None


def test_person_is_registered_by_app_ready() -> None:
    spec = get_zoho_spec(Person)
    assert spec is not None
    assert spec.kind == "contact"
    assert spec.auto_push is True


def test_webhook_url_reads_settings() -> None:
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        assert webhook_url("contact") == CONTACT_URL
        assert webhook_url("enquiry") == ""
        assert webhook_url("unknown") == ""


def test_test_settings_hard_disable_all_webhooks() -> None:
    """Hermetic suite: a developer's populated .env must never make tests POST
    factory PII to the sandbox CRM — settings/test.py pins every kind to ""."""
    from django.conf import settings

    assert settings.ZOHO_FLOW_WEBHOOKS == {
        "contact": "",
        "enquiry": "",
        "quote": "",
        "booking": "",
    }


def test_httpx_logger_is_pinned_to_warning() -> None:
    """httpx logs the full request URL at INFO — for Zoho Flow that URL carries
    the zapikey credential, so the LOGGING dict must pin httpx ≥ WARNING."""
    from django.conf import settings

    assert settings.LOGGING["loggers"]["httpx"]["level"] == "WARNING"


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately", "contact_webhook")
def test_reregister_is_idempotent_single_enqueue_per_save(delay_mock: mock.Mock) -> None:
    """Re-registering Person must not double-connect the post_save handler."""
    spec = get_zoho_spec(Person)
    assert spec is not None
    register_zoho_flow(Person, kind="contact", build_payload=spec.build_payload)

    _person()

    assert SyncRecord.objects.count() == 1
    assert delay_mock.call_count == 1


# --- enqueue --------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately", "contact_webhook")
def test_person_save_creates_pending_record_and_dispatches(delay_mock: mock.Mock) -> None:
    person = _person()

    record = SyncRecord.objects.get()
    assert record.content_type == _person_ct()
    assert record.object_id == person.pk
    assert record.provider == SyncProvider.ZOHO_CRM
    assert record.direction == SyncDirection.PUSH
    assert record.status == SyncStatus.PENDING
    delay_mock.assert_called_once_with(record.pk)


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_dispatch_defers_until_commit(
    delay_mock: mock.Mock,
    django_capture_on_commit_callbacks: Any,
) -> None:
    with django_capture_on_commit_callbacks() as callbacks:
        _person()

    assert delay_mock.call_count == 0
    for callback in callbacks:
        callback()
    assert delay_mock.call_count == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately", "contact_webhook")
def test_enqueue_bumps_existing_non_pending_row(delay_mock: mock.Mock) -> None:
    person = _person()
    record = SyncRecord.objects.get()
    _mark_in_sync(record)

    person.first_name = "Changed"
    person.save()

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    assert SyncRecord.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately")
def test_unset_url_is_full_noop(delay_mock: mock.Mock) -> None:
    _person()

    assert SyncRecord.objects.count() == 0
    delay_mock.assert_not_called()


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately", "contact_webhook")
def test_suppression_is_full_noop(delay_mock: mock.Mock) -> None:
    with suppress_zoho_push():
        _person()

    assert SyncRecord.objects.count() == 0
    delay_mock.assert_not_called()

    _person()  # enqueue works again after the context exits
    assert SyncRecord.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately")
def test_anonymized_person_never_enqueued(delay_mock: mock.Mock) -> None:
    person = _person()  # URL unset here → no record
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        person.anonymize()
        assert SyncRecord.objects.count() == 0

        enqueue_zoho_push(person)
        assert SyncRecord.objects.count() == 0
    delay_mock.assert_not_called()


# --- PersonEmail / PersonPhone child edits --------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately", "contact_webhook", "delay_mock")
def test_person_email_save_and_delete_bump_parent() -> None:
    person = _person()
    record = SyncRecord.objects.get()
    _mark_in_sync(record)

    email = PersonEmail.objects.create(contact=person, email="ada@example.com", is_primary=True)
    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING

    _mark_in_sync(record)
    email.delete()
    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    assert SyncRecord.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately", "contact_webhook", "delay_mock")
def test_person_phone_save_and_delete_bump_parent() -> None:
    person = _person()
    record = SyncRecord.objects.get()
    _mark_in_sync(record)

    phone = PersonPhone.objects.create(contact=person, number="+447700900123", is_primary=True)
    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING

    _mark_in_sync(record)
    phone.delete()
    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING


# --- post_delete reaper ---------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately", "contact_webhook", "delay_mock")
def test_delete_registered_target_reaps_its_zoho_sync_records() -> None:
    """FG-007 mirror for the zoho registry: GenericFK can't cascade, so
    deleting a registered target must remove its ZOHO_CRM SyncRecords —
    other providers' rows for the same target survive."""
    person = _person()
    assert SyncRecord.objects.count() == 1
    SyncRecord.objects.create(
        content_type=_person_ct(),
        object_id=person.pk,
        provider=SyncProvider.FLYWIRE.value,
        direction=SyncDirection.PUSH.value,
        status=SyncStatus.PENDING.value,
    )

    person.delete()

    remaining = list(SyncRecord.objects.values_list("provider", flat=True))
    assert remaining == [SyncProvider.FLYWIRE.value]


# --- person_merged --------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately")
def test_person_merge_enqueues_survivor(delay_mock: mock.Mock) -> None:
    survivor = _person()
    absorbed = _person()

    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        absorbed.merge(survivor)

    record = SyncRecord.objects.get(content_type=_person_ct(), object_id=survivor.pk)
    assert record.status == SyncStatus.PENDING


# --- push_sync_record -----------------------------------------------------


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("POST", CONTACT_URL))


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_push_success_marks_in_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    person = _person(first_name="Ada", last_name="Lovelace")
    record = _make_record(person.pk)
    record.error_message = "previous failure"
    record.retry_count = 3  # an old, completed retry chain
    record.save(update_fields=["error_message", "retry_count", "updated_at"])
    record.refresh_from_db()
    post = mock.Mock(return_value=_response(200))
    monkeypatch.setattr(tasks.httpx, "post", post)

    push_sync_record(record.pk)

    assert post.call_count == 1
    assert post.call_args.args == (CONTACT_URL,)
    payload = post.call_args.kwargs["json"]
    assert payload["RES_ID"] == person.pk
    record.refresh_from_db()
    assert record.status == SyncStatus.IN_SYNC
    assert record.last_pushed_at is not None
    assert record.error_message == ""
    # Reset, not lifetime-cumulative — else an old chain's count makes the
    # next transient blip exhaust after a couple of attempts.
    assert record.retry_count == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_push_success_yields_to_concurrent_bump(monkeypatch: pytest.MonkeyPatch) -> None:
    """A PENDING bump written between the task's read and its success write
    must win — stamping IN_SYNC over it could strand an edit whose own
    dispatch was lost (the sweep only repairs PENDING rows)."""
    person = _person()
    record = _make_record(person.pk)

    def _bump_then_ok(url: str, **kwargs: Any) -> httpx.Response:
        SyncRecord.objects.filter(pk=record.pk).update(updated_at=timezone.now())
        return _response(200)

    monkeypatch.setattr(tasks.httpx, "post", mock.Mock(side_effect=_bump_then_ok))

    push_sync_record(record.pk)

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    assert record.last_pushed_at is None


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_push_4xx_is_permanent_error_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    person = _person()
    record = _make_record(person.pk)
    post = mock.Mock(return_value=_response(422))
    monkeypatch.setattr(tasks.httpx, "post", post)

    push_sync_record(record.pk)  # must not raise

    assert post.call_count == 1
    record.refresh_from_db()
    assert record.status == SyncStatus.ERROR
    assert "422" in record.error_message
    assert record.retry_count == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_push_5xx_bumps_retry_count_and_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    person = _person()
    record = _make_record(person.pk)
    post = mock.Mock(return_value=_response(503))
    monkeypatch.setattr(tasks.httpx, "post", post)

    with pytest.raises(TransientPushError):
        push_sync_record(record.pk)

    record.refresh_from_db()
    assert record.retry_count == 1
    assert record.status == SyncStatus.PENDING
    assert "503" in record.error_message


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_push_transport_error_bumps_retry_count_and_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    person = _person()
    record = _make_record(person.pk)
    post = mock.Mock(side_effect=httpx.ConnectError("boom"))
    monkeypatch.setattr(tasks.httpx, "post", post)

    with pytest.raises(httpx.ConnectError):
        push_sync_record(record.pk)

    record.refresh_from_db()
    assert record.retry_count == 1
    assert record.status == SyncStatus.PENDING


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_push_exhaustion_marks_error_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    person = _person()
    record = _make_record(person.pk)
    record.retry_count = 6
    record.save(update_fields=["retry_count", "updated_at"])
    post = mock.Mock(return_value=_response(503))
    monkeypatch.setattr(tasks.httpx, "post", post)

    push_sync_record(record.pk)  # exhausted — must not raise

    record.refresh_from_db()
    assert record.status == SyncStatus.ERROR


@pytest.mark.django_db
def test_push_missing_record_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    post = mock.Mock()
    monkeypatch.setattr(tasks.httpx, "post", post)

    push_sync_record(10**9)

    post.assert_not_called()


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_push_missing_target_deletes_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backstop for anything the post_delete reaper missed: a SyncRecord
    without a target is meaningless — left PENDING it would clog the sweep's
    per-tick cap forever."""
    record = _make_record(10**6)  # no Person with this pk
    post = mock.Mock()
    monkeypatch.setattr(tasks.httpx, "post", post)

    push_sync_record(record.pk)

    post.assert_not_called()
    assert not SyncRecord.objects.filter(pk=record.pk).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_push_anonymized_target_disables_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anonymized between enqueue and delivery → park DISABLED (never push,
    keep the ops trail, drop out of the PENDING sweep)."""
    person = _person()
    record = _make_record(person.pk)
    person.anonymize()
    post = mock.Mock()
    monkeypatch.setattr(tasks.httpx, "post", post)

    push_sync_record(record.pk)

    post.assert_not_called()
    record.refresh_from_db()
    assert record.status == SyncStatus.DISABLED


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_push_builder_exception_parks_record_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken payload builder is a poison pill (task fails, row stays
    PENDING, sweep re-dispatches every tick) — park it ERROR instead."""
    person = _person()
    record = _make_record(person.pk)

    def _boom(instance: Any) -> dict[str, Any]:
        raise RuntimeError("builder exploded")

    spec = ZohoFlowSpec(kind="contact", build_payload=_boom, auto_push=True)
    monkeypatch.setattr(tasks, "get_zoho_spec", lambda model: spec)
    post = mock.Mock()
    monkeypatch.setattr(tasks.httpx, "post", post)

    push_sync_record(record.pk)  # must not raise

    post.assert_not_called()
    record.refresh_from_db()
    assert record.status == SyncStatus.ERROR
    assert "RuntimeError" in record.error_message
    assert "builder exploded" in record.error_message


@pytest.mark.django_db
def test_push_unset_url_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    person = _person()
    record = _make_record(person.pk)
    post = mock.Mock()
    monkeypatch.setattr(tasks.httpx, "post", post)

    push_sync_record(record.pk)

    post.assert_not_called()
    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING


# --- push_pending sweep ---------------------------------------------------


def _age(record: SyncRecord, *, minutes: int) -> None:
    SyncRecord.objects.filter(pk=record.pk).update(
        updated_at=timezone.now() - timedelta(minutes=minutes)
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_sweep_respects_grace_window(delay_mock: mock.Mock) -> None:
    old = _make_record(1001)
    _age(old, minutes=30)
    fresh = _make_record(1002)
    _age(fresh, minutes=5)

    dispatched = push_pending()

    assert dispatched == 1
    delay_mock.assert_called_once_with(old.pk)


@pytest.mark.django_db
def test_sweep_skips_kinds_without_url(delay_mock: mock.Mock) -> None:
    record = _make_record(1001)
    _age(record, minutes=30)

    dispatched = push_pending()

    assert dispatched == 0
    delay_mock.assert_not_called()


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_sweep_excludes_unregistered_content_types(delay_mock: mock.Mock) -> None:
    record = _make_record(
        1001,
        content_type=ContentType.objects.get_for_model(Property),
    )
    _age(record, minutes=30)

    dispatched = push_pending()

    assert dispatched == 0
    delay_mock.assert_not_called()


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_sweep_excludes_non_pending_records(delay_mock: mock.Mock) -> None:
    record = _make_record(1001, status=SyncStatus.ERROR.value)
    _age(record, minutes=30)

    assert push_pending() == 0
    delay_mock.assert_not_called()


@pytest.mark.django_db
@pytest.mark.usefixtures("contact_webhook")
def test_sweep_caps_batch_and_dispatches_oldest_first(delay_mock: mock.Mock) -> None:
    ct = _person_ct()
    records = SyncRecord.objects.bulk_create(
        SyncRecord(
            content_type=ct,
            object_id=100_000 + i,
            provider=SyncProvider.ZOHO_CRM.value,
            direction=SyncDirection.PUSH.value,
            status=SyncStatus.PENDING.value,
        )
        for i in range(205)
    )
    # Stagger ages: index 0 is the OLDEST; the last 5 are the freshest (but
    # still beyond the grace window) and must be the ones left behind.
    base = timezone.now() - timedelta(hours=10)
    for i, record in enumerate(records):
        SyncRecord.objects.filter(pk=record.pk).update(updated_at=base + timedelta(seconds=i))

    dispatched = push_pending()

    assert dispatched == 200
    called_pks = [call.args[0] for call in delay_mock.call_args_list]
    expected = [r.pk for r in records[:200]]
    assert called_pks == expected
