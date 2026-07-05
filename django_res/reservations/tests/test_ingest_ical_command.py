"""The `ingest_ical` management command wires the cron entry point to the poller.

Thin coverage: the reconciliation logic is exercised in `test_ical_ingest.py`;
here we only assert the command resolves its target, calls the service, and
prints a summary — and that `--property-id` scopes to one villa.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from io import StringIO
from typing import TYPE_CHECKING, cast

import httpx
import pytest
import respx
import time_machine
from django.core.management import call_command
from django.core.management.base import CommandError

from properties.factories import PropertyCalendarFeedFactory
from reservations.enums import OwnerBlockSource
from reservations.models import OwnerBlock

if TYPE_CHECKING:
    from properties.models import Property, PropertyCalendarFeed

pytestmark = pytest.mark.django_db

# The mocked feed carries literal July-2026 events and the ingest window opens
# at "today", so the clock must sit before the fixtures for events to import.
FROZEN_TODAY = "2026-06-01"


@pytest.fixture(autouse=True)
def _frozen_clock() -> Iterator[None]:
    with time_machine.travel(FROZEN_TODAY, tick=False):
        yield


_ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//EN\r\n"
    "BEGIN:VEVENT\r\nUID:e1\r\nSUMMARY:Reserved\r\n"
    "DTSTART;VALUE=DATE:20260701\r\nDTEND;VALUE=DATE:20260705\r\n"
    "END:VEVENT\r\nEND:VCALENDAR\r\n"
)


def _feed(property_: Property, url: str) -> PropertyCalendarFeed:
    return cast(
        "PropertyCalendarFeed",
        PropertyCalendarFeedFactory(property=property_, url=url, label="Airbnb"),
    )


@respx.mock
def test_command_ingests_single_property(property_: Property) -> None:
    url = "https://example.test/cmd.ics"
    _feed(property_, url)
    respx.get(url).mock(return_value=httpx.Response(200, text=_ICS))

    out = StringIO()
    call_command("ingest_ical", "--property-id", str(property_.pk), stdout=out)

    assert "1 blocks created" in out.getvalue()
    assert OwnerBlock.objects.filter(
        property=property_,
        source=OwnerBlockSource.ICAL.value,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 5),
    ).exists()


def test_command_rejects_unknown_property() -> None:
    with pytest.raises(CommandError):
        call_command("ingest_ical", "--property-id", "999999")
