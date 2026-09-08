"""GAP-102 unit 4: an `Extra` save/delete re-pushes its villa.

The catalogue rides the villa payload (option (a)), so a catalogue edit
that never touches the Property row still has to bump the villa's Zoho
push — exactly one push per edit, never one per booking that used the
extra. Receiver lives here (not `properties.signals`) because `pricing`
sits ABOVE `properties` on the import spine.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast
from unittest import mock

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from integrations import tasks
from integrations.enums import SyncProvider, SyncStatus
from integrations.models import SyncRecord
from integrations.services.zoho_flow import suppress_zoho_push
from pricing.factories import ExtraFactory
from pricing.models import Extra
from properties.factories import PropertyFactory
from properties.models.property import Property

VILLA_URL = "https://flow.zoho.example/villa"
WEBHOOKS = {"contact": "", "villa": VILLA_URL, "enquiry": "", "quote": "", "booking": ""}

pytestmark = pytest.mark.django_db


@pytest.fixture
def villa_webhook() -> Iterator[None]:
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        yield


@pytest.fixture
def delay_mock(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    m = mock.Mock()
    monkeypatch.setattr(tasks.push_sync_record, "delay", m)
    return m


def _property(**kwargs: Any) -> Property:
    return cast(Property, PropertyFactory(**kwargs))


def _extra(**kwargs: Any) -> Extra:
    return cast(Extra, ExtraFactory(**kwargs))


def _records_for(prop: Property) -> list[SyncRecord]:
    return list(
        SyncRecord.objects.filter(
            content_type=ContentType.objects.get_for_model(Property),
            object_id=prop.pk,
            provider=SyncProvider.ZOHO_CRM.value,
        )
    )


def _synced_property(delay_mock: mock.Mock) -> tuple[Property, SyncRecord]:
    prop = _property()
    (record,) = _records_for(prop)
    record.status = SyncStatus.IN_SYNC.value
    record.save(update_fields=["status", "updated_at"])
    delay_mock.reset_mock()
    return prop, record


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_extra_save_bumps_villa_exactly_once(delay_mock: mock.Mock) -> None:
    prop, record = _synced_property(delay_mock)

    _extra(property=prop)

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    assert len(_records_for(prop)) == 1
    delay_mock.assert_called_once_with(record.pk)


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_two_extras_in_one_transaction_share_one_pending_record(
    delay_mock: mock.Mock,
) -> None:
    """The bump dedupes on the villa's PENDING row — a bulk catalogue edit is
    one villa push, not one per row."""
    prop, record = _synced_property(delay_mock)

    with transaction.atomic():
        _extra(property=prop, name="Cleaning")
        _extra(property=prop, name="Heating")

    assert len(_records_for(prop)) == 1
    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    delay_mock.assert_called_once_with(record.pk)


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_extra_delete_bumps_villa(delay_mock: mock.Mock) -> None:
    prop = _property()
    extra = _extra(property=prop)
    (record,) = _records_for(prop)
    record.status = SyncStatus.IN_SYNC.value
    record.save(update_fields=["status", "updated_at"])
    delay_mock.reset_mock()

    extra.delete()

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    delay_mock.assert_called_once_with(record.pk)


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_extra_save_is_noop_when_villa_url_unset_without_parent_select(
    delay_mock: mock.Mock,
) -> None:
    """The receiver guards on the URL BEFORE dereferencing the villa, so an
    unset webhook (dev) costs no Property SELECT — mirrors
    `properties/tests/test_zoho_villa.py::test_unset_url_child_bump_is_noop_without_parent_select`."""
    with override_settings(ZOHO_FLOW_WEBHOOKS={**WEBHOOKS, "villa": ""}):
        prop = _property()  # no webhook → no record for the create either
        extra = Extra.objects.get(pk=_extra(property=prop).pk)

        with CaptureQueriesContext(connection) as ctx:
            extra.save()

    assert not [q for q in ctx.captured_queries if '"properties_property"' in q["sql"]]
    assert _records_for(prop) == []
    delay_mock.assert_not_called()


@pytest.mark.usefixtures("run_on_commit_immediately", "villa_webhook")
def test_extra_save_is_noop_under_suppression(delay_mock: mock.Mock) -> None:
    prop, record = _synced_property(delay_mock)

    with suppress_zoho_push():
        _extra(property=prop)

    record.refresh_from_db()
    assert record.status == SyncStatus.IN_SYNC
    delay_mock.assert_not_called()
