"""Smoke tests for the `demo_ical` management command.

The command is demo scaffolding, not product code, so these tests only pin the
load-bearing behaviour: a feed imports a block, the owner calendar API reflects
it, `--reset` cleans up, and `--inject-conflict` arms the conflict alert. The
import *logic* itself is covered exhaustively by `test_ical_ingest.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from io import StringIO
from typing import cast

import httpx
import pytest
import respx
import time_machine
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import User
from comms.models import EmailLog
from properties.models import Property, PropertyCalendarFeed
from reservations.enums import OwnerBlockSource, OwnerBlockStatus
from reservations.management.commands.demo_ical import GUEST_EMAIL, PROPERTY_SLUG
from reservations.models import OwnerBlock

pytestmark = pytest.mark.django_db

# The mocked feed carries literal July-2026 events and the ingest window opens
# at "today", so the clock must sit before the fixtures for events to import.
FROZEN_TODAY = "2026-06-01"


@pytest.fixture(autouse=True)
def _frozen_clock() -> Iterator[None]:
    with time_machine.travel(FROZEN_TODAY, tick=False):
        yield


_FEED_URL = "https://demo.test/calendar.ics"


def _ics(start: str, end: str) -> str:
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//demo//EN\r\n"
        f"BEGIN:VEVENT\r\nUID:demo-1\r\nSUMMARY:Reserved\r\n"
        f"DTSTART;VALUE=DATE:{start}\r\nDTEND;VALUE=DATE:{end}\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )


def _run(*args: str) -> str:
    out = StringIO()
    call_command("demo_ical", *args, stdout=out, stderr=out)
    return out.getvalue()


@respx.mock
def test_setup_add_feed_and_poll_imports_a_block() -> None:
    respx.get(_FEED_URL).mock(return_value=httpx.Response(200, text=_ics("20260701", "20260705")))

    _run("--setup")
    _run("--add-feed", "--feed-url", _FEED_URL, "--platform", "google", "--label", "Owner cal")
    output = _run("--poll")

    prop = Property.objects.get(slug=PROPERTY_SLUG)
    block = OwnerBlock.objects.get(property=prop, source=OwnerBlockSource.ICAL.value)
    assert block.status == OwnerBlockStatus.APPROVED.value
    assert block.created_by_id is None
    assert block.date_from == date(2026, 7, 1)
    assert block.date_to == date(2026, 7, 5)
    assert "created=1" in output
    assert "BLOCKED (owner_block)" in output
    # Inclusive nights, not the raw half-open [from, to): [07-01, 07-05) is 4
    # nights ending the 4th, with the 5th free as a checkout/arrival day.
    assert "2026-07-01 - 2026-07-04  (4 nights, free from 2026-07-05)" in output
    assert "2026-07-05" in output and "OPEN — checkout / available" in output


@respx.mock
def test_repoll_is_idempotent() -> None:
    respx.get(_FEED_URL).mock(return_value=httpx.Response(200, text=_ics("20260701", "20260705")))
    _run("--setup")
    _run("--add-feed", "--feed-url", _FEED_URL)

    _run("--poll")
    output = _run("--poll")

    prop = Property.objects.get(slug=PROPERTY_SLUG)
    assert (
        OwnerBlock.objects.filter(
            property=prop,
            source=OwnerBlockSource.ICAL.value,
            status=OwnerBlockStatus.APPROVED.value,
        ).count()
        == 1
    )
    assert "created=0" in output


@respx.mock
def test_owner_calendar_api_surfaces_the_block() -> None:
    respx.get(_FEED_URL).mock(return_value=httpx.Response(200, text=_ics("20260701", "20260705")))
    _run("--setup", "--owner-email", "owner@demo.test", "--owner-password", "pw12345678")
    _run("--add-feed", "--feed-url", _FEED_URL)
    _run("--poll")

    prop = Property.objects.get(slug=PROPERTY_SLUG)
    client = APIClient()
    client.force_authenticate(User.objects.get(email="owner@demo.test"))
    resp = client.get(f"/api/v1/owner/properties/{prop.pk}/calendar?from=2026-07-01&to=2026-07-05")

    assert resp.status_code == 200
    cells = {c["date"]: c for c in resp.json()["cells"]}
    assert cells["2026-07-01"]["available"] is False
    assert cells["2026-07-01"]["reason"] == "owner_block"


@respx.mock
@override_settings(OPS_EMAIL_RECIPIENTS=["ops@villacollective.test"])
@pytest.mark.usefixtures("run_on_commit_immediately", "system_profile")
def test_inject_conflict_then_poll_fires_ops_alert() -> None:
    respx.get(_FEED_URL).mock(return_value=httpx.Response(200, text=_ics("20260701", "20260705")))
    _run("--setup")
    _run("--add-feed", "--feed-url", _FEED_URL)
    _run("--poll")

    _run("--inject-conflict", "quotation")
    output = _run("--poll")

    assert "conflicts=1" in output
    log = EmailLog.objects.get(template_key="ical.conflict")
    assert log.to == ["ops@villacollective.test"]
    assert "quotation" in log.rendered_body


def test_inject_conflict_without_ops_recipients_refuses() -> None:
    _run("--setup")
    with pytest.raises(CommandError, match="OPS_EMAIL_RECIPIENTS is empty"):
        _run("--inject-conflict", "quotation")


@respx.mock
def test_reset_removes_demo_data() -> None:
    respx.get(_FEED_URL).mock(return_value=httpx.Response(200, text=_ics("20260701", "20260705")))
    _run("--setup")
    _run("--add-feed", "--feed-url", _FEED_URL)
    _run("--poll")

    _run("--reset")

    assert not Property.objects.filter(slug=PROPERTY_SLUG).exists()
    assert not PropertyCalendarFeed.objects.filter(url=_FEED_URL).exists()
    assert not OwnerBlock.objects.filter(idempotency_key="2026-07-01_2026-07-05").exists()


@respx.mock
@override_settings(OPS_EMAIL_RECIPIENTS=["ops@villacollective.test"])
@pytest.mark.usefixtures("system_profile")
def test_reset_after_booking_conflict_cleans_up() -> None:
    """A booking clash leaves a PROTECT-heavy Booking; --reset must still unwind it."""
    respx.get(_FEED_URL).mock(return_value=httpx.Response(200, text=_ics("20260701", "20260705")))
    _run("--setup")
    _run("--add-feed", "--feed-url", _FEED_URL)
    _run("--poll")
    _run("--inject-conflict", "booking")

    from accounts.models import Person

    # The demo customer is a CUSTOMER Person; the booking-clash enquiry it owns
    # is reachable via its primary email.
    assert Person.objects.filter(emails__email=GUEST_EMAIL).exists()

    _run("--reset")  # would raise ProtectedError if the Booking weren't deleted

    from reservations.models import Booking

    assert not Property.objects.filter(slug=PROPERTY_SLUG).exists()
    assert not Booking.objects.filter(person__emails__email=GUEST_EMAIL).exists()
    # The customer Person (and its PII-bearing email/phone children) must not be
    # stranded — otherwise rows accumulate and --reset stops being idempotent.
    assert not Person.objects.filter(emails__email=GUEST_EMAIL).exists()


@respx.mock
@override_settings(OPS_EMAIL_RECIPIENTS=["ops@villacollective.test"])
@pytest.mark.usefixtures("system_profile")
def test_reset_clears_protecting_rows_on_property() -> None:
    """Reset must unwind every PROTECT-ing row on the demo property: a booking's
    Payment/BookingEvent, a RatePlan, and a *non-demo-guest* QuotationLine."""
    respx.get(_FEED_URL).mock(return_value=httpx.Response(200, text=_ics("20260701", "20260705")))
    _run("--setup")
    _run("--add-feed", "--feed-url", _FEED_URL)
    _run("--poll")
    _run("--inject-conflict", "booking")

    from datetime import date, timedelta
    from decimal import Decimal

    from django.utils import timezone

    from accounts.factories import CustomerPersonFactory
    from accounts.models import Person
    from payments.enums import PaymentPurpose
    from payments.models import Payment
    from pricing.models import Currency, RatePlan
    from reservations.enums import BookingStatus, EnquiryEventKind, EnquiryStatus
    from reservations.models import (
        Booking,
        BookingEvent,
        Enquiry,
        EnquiryEvent,
        Quotation,
        QuotationLine,
        TermsVersion,
    )

    prop = Property.objects.get(slug=PROPERTY_SLUG)
    booking = Booking.objects.get(property=prop)
    gbp, _ = Currency.objects.get_or_create(
        code="GBP", defaults={"name": "Pound sterling", "symbol": "£"}
    )
    Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT,
        amount=Decimal("100.00"),
        currency=gbp,
    )
    BookingEvent.objects.create(
        booking=booking,
        from_status=BookingStatus.DRAFT,
        to_status=BookingStatus.AWAITING_DEPOSIT,
    )
    # A RatePlan PROTECTs the property.
    RatePlan.objects.create(
        property=prop,
        currency=gbp,
        name="summer",
        effective_from=date(2026, 6, 1),
        effective_to=date(2026, 9, 1),
    )
    # A QuotationLine on the property from an unrelated customer (not the demo
    # guest) — the case that broke the original guest-scoped teardown.
    other_customer = cast(Person, CustomerPersonFactory(primary_email="someone.else@demo.test"))
    # An EnquiryEvent PROTECTs its enquiry — the orphaned-enquiry teardown must
    # clear it.
    other_enquiry = Enquiry.objects.create(
        person=other_customer, email=other_customer.primary_email() or ""
    )
    EnquiryEvent.objects.create(
        enquiry=other_enquiry,
        from_status=EnquiryStatus.NEW,
        to_status=EnquiryStatus.QUOTE_SENT,
        kind=EnquiryEventKind.QUOTE_SENT,
    )
    terms = TermsVersion.objects.create(
        version="2026-test", body_markdown="x", published_at=timezone.now()
    )
    quotation = Quotation.objects.create(
        enquiry=other_enquiry,
        person=other_customer,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    QuotationLine.objects.create(
        quotation=quotation,
        property=prop,
        currency=gbp,
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 8),
        adults=2,
        total=Decimal("1400.00"),
    )

    _run("--reset")  # would raise ProtectedError if any PROTECT-ing row survived

    assert not Property.objects.filter(slug=PROPERTY_SLUG).exists()
    assert not Booking.objects.filter(person__emails__email=GUEST_EMAIL).exists()


@respx.mock
@override_settings(OPS_EMAIL_RECIPIENTS=["ops@villacollective.test"])
@pytest.mark.usefixtures("system_profile")
def test_reset_after_quotation_conflict_clears_person_mirror() -> None:
    """The quotation-clash path links its Quotation/Enquiry to a Person; --reset
    must remove the demo rows AND the stranded Person mirror."""
    respx.get(_FEED_URL).mock(return_value=httpx.Response(200, text=_ics("20260701", "20260705")))
    _run("--setup")
    _run("--add-feed", "--feed-url", _FEED_URL)
    _run("--poll")
    _run("--inject-conflict", "quotation")

    from accounts.models import Person

    assert Person.objects.filter(emails__email=GUEST_EMAIL).exists()

    _run("--reset")

    from reservations.models import Quotation

    assert not Property.objects.filter(slug=PROPERTY_SLUG).exists()
    assert not Quotation.objects.filter(person__emails__email=GUEST_EMAIL).exists()
    assert not Person.objects.filter(emails__email=GUEST_EMAIL).exists()


@respx.mock
@override_settings(OPS_EMAIL_RECIPIENTS=["ops@villacollective.test"])
@pytest.mark.usefixtures("system_profile")
def test_repeated_setup_reset_does_not_accumulate_person_mirrors() -> None:
    """Idempotency regression: two full setup→conflict→reset cycles must leave
    zero demo Person mirrors behind, not one per cycle."""
    respx.get(_FEED_URL).mock(return_value=httpx.Response(200, text=_ics("20260701", "20260705")))
    from accounts.models import Person

    for _ in range(2):
        _run("--setup")
        _run("--add-feed", "--feed-url", _FEED_URL)
        _run("--poll")
        _run("--inject-conflict", "booking")
        _run("--reset")

    assert Person.objects.filter(emails__email=GUEST_EMAIL).count() == 0


def test_reset_cleans_up_custom_owner_email() -> None:
    _run("--setup", "--owner-email", "custom.owner@demo.test", "--owner-password", "pw12345678")
    _run("--reset")
    assert not User.objects.filter(email="custom.owner@demo.test").exists()
