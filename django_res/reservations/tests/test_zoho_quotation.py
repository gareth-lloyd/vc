"""Tests for the Quotation → Zoho Flow push on send (GAP-081 Unit 3).

Quotation registers with `auto_push=False`: drafts must NEVER auto-push; the
only enqueue path is `record_quote_sent` (both the SMTP and manual-mark send
paths route through it). Registered by `reservations.apps.ready()` — never
unregistered in tests (xdist worker leak); behaviour toggled via
`override_settings(ZOHO_FLOW_WEBHOOKS=…)`.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest import mock

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.utils import timezone

from integrations import tasks
from integrations.enums import SyncProvider, SyncStatus
from integrations.models import SyncRecord
from integrations.services.zoho_flow import get_zoho_spec
from reservations.models import Quotation, QuotationLine
from reservations.services.quotation_transmission import (
    SEND_PATH_MANUAL,
    SEND_PATH_SMTP,
    record_quote_sent,
)
from reservations.services.zoho_payload import build_quotation_payload

if TYPE_CHECKING:
    from accounts.models import Person
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import Enquiry, TermsVersion

QUOTE_URL = "https://flow.zoho.example/quote"
WEBHOOKS = {"contact": "", "enquiry": "", "quote": QUOTE_URL, "booking": ""}


@pytest.fixture
def delay_mock(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    m = mock.Mock()
    monkeypatch.setattr(tasks.push_sync_record, "delay", m)
    return m


@pytest.fixture
def enquiry(customer: Person) -> Enquiry:
    from reservations.models import Enquiry

    return Enquiry.objects.create(person=customer, adults=2)


@pytest.fixture
def quotation(
    enquiry: Enquiry,
    customer: Person,
    terms: TermsVersion,
) -> Quotation:
    return Quotation.objects.create(
        enquiry=enquiry,
        person=customer,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )


@pytest.fixture
def line(quotation: Quotation, property_: Property, gbp: Currency) -> QuotationLine:
    return QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        children=1,
        total=Decimal("1400.00"),
        discount=Decimal("100.00"),
        pricing_snapshot={"basis": "GROSS", "nightly": "200.00"},
        is_selected=True,
    )


def _quotation_ct() -> ContentType:
    return ContentType.objects.get_for_model(Quotation)


def _records_for(quotation: Quotation) -> list[SyncRecord]:
    return list(
        SyncRecord.objects.filter(
            content_type=_quotation_ct(),
            object_id=quotation.pk,
            provider=SyncProvider.ZOHO_CRM.value,
        )
    )


# --- registration ---------------------------------------------------------


def test_quotation_is_registered_with_auto_push_off() -> None:
    spec = get_zoho_spec(Quotation)
    assert spec is not None
    assert spec.kind == "quote"
    assert spec.auto_push is False
    assert spec.build_payload is build_quotation_payload


# --- payload --------------------------------------------------------------


@pytest.mark.django_db
def test_payload_header_fields(quotation: Quotation, line: QuotationLine) -> None:
    payload = build_quotation_payload(quotation)

    assert payload["RES_ID"] == quotation.pk
    assert payload["id"] == quotation.pk
    assert payload["reference"] == quotation.reference
    assert payload["number"] == quotation.number
    assert payload["status"] == quotation.status
    assert quotation.expires_at is not None
    assert payload["expires_at"] == quotation.expires_at.isoformat()
    assert payload["is_unbranded"] is False
    assert payload["terms_version"]["version"] == quotation.terms_version.version

    enquiry_sub = payload["enquiry"]
    assert enquiry_sub["RES_ID"] == quotation.enquiry_id
    assert enquiry_sub["reference"] == quotation.enquiry.reference

    person_sub = payload["person"]
    assert person_sub["RES_ID"] == quotation.person_id
    assert payload["full_name"] == person_sub["full_name"]
    assert payload["agent"] is None


@pytest.mark.django_db
def test_payload_covers_quotation_post_data_minimums(
    quotation: Quotation, line: QuotationLine
) -> None:
    """`QuotationPostData` (legacy zoho-crm.md) mapped onto current models,
    snake_case: Name/Account/Contact→full_name+person, Stage→status,
    Valid_Until→expires_at, Enquiry.RES_ID→enquiry, T&C→terms_version,
    Arrival/Departure/No_of_Nights/No_of_Guests/Country/Region/Villa/
    Currency/money/Line_Items→lines[] (per-line on the current model)."""
    payload = build_quotation_payload(quotation)
    minimum = {
        "RES_ID",
        "id",
        "full_name",
        "status",
        "expires_at",
        "person",
        "agent",
        "enquiry",
        "terms_version",
        "lines",
    }
    assert minimum <= payload.keys()

    line_minimum = {
        "RES_ID",
        "id",
        "property",
        "currency",
        "date_from",
        "date_to",
        "nights",
        "adults",
        "children",
        "total",
        "discount",
        "pricing_snapshot",
    }
    assert line_minimum <= payload["lines"][0].keys()


@pytest.mark.django_db
def test_payload_line_shape(quotation: Quotation, line: QuotationLine) -> None:
    payload = build_quotation_payload(quotation)

    (line_sub,) = payload["lines"]
    assert line_sub["RES_ID"] == line.pk
    assert line_sub["id"] == line.pk
    assert line_sub["property"]["RES_ID"] == line.property_id
    assert line_sub["property"]["name"] == line.property.name
    assert line_sub["currency"] == "GBP"
    assert line_sub["date_from"] == "2026-06-10"
    assert line_sub["date_to"] == "2026-06-17"
    assert line_sub["nights"] == 7
    assert line_sub["adults"] == 2
    assert line_sub["children"] == 1
    # Money as strings — Decimals are not JSON-serialisable and floats drift.
    assert line_sub["total"] == "1400.00"
    assert line_sub["discount"] == "100.00"
    assert line_sub["pricing_snapshot"] == {"basis": "GROSS", "nightly": "200.00"}
    assert line_sub["is_selected"] is True


@pytest.mark.django_db
def test_payload_excludes_synthetic_booking_lines(
    quotation: Quotation,
    line: QuotationLine,
    property_: Property,
    gbp: Currency,
) -> None:
    QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        adults=2,
        legacy_id="booking-99",
    )

    payload = build_quotation_payload(quotation)

    assert [sub["RES_ID"] for sub in payload["lines"]] == [line.pk]


@pytest.mark.django_db
def test_payload_anonymized_person_fails_closed(quotation: Quotation, line: QuotationLine) -> None:
    quotation.person.anonymize()
    quotation.refresh_from_db()

    payload = build_quotation_payload(quotation)

    assert payload["person"] is None
    assert payload["full_name"] == ""
    assert "[REDACTED]" not in json.dumps(payload)


@pytest.mark.django_db
def test_payload_json_round_trips(quotation: Quotation, line: QuotationLine) -> None:
    payload = build_quotation_payload(quotation)
    assert json.loads(json.dumps(payload)) == payload


# --- enqueue wiring -------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately")
def test_draft_save_does_not_enqueue(quotation: Quotation, delay_mock: mock.Mock) -> None:
    """auto_push=False: draft edits must never push, even with the URL set."""
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        quotation.is_unbranded = True
        quotation.save()

    assert _records_for(quotation) == []
    delay_mock.assert_not_called()


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately")
def test_record_quote_sent_smtp_enqueues_pending(
    quotation: Quotation, delay_mock: mock.Mock
) -> None:
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        record_quote_sent(quotation, send_path=SEND_PATH_SMTP)

    (record,) = _records_for(quotation)
    assert record.status == SyncStatus.PENDING
    delay_mock.assert_any_call(record.pk)


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately")
def test_record_quote_sent_manual_enqueues_pending(
    quotation: Quotation, delay_mock: mock.Mock
) -> None:
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        record_quote_sent(quotation, send_path=SEND_PATH_MANUAL)

    (record,) = _records_for(quotation)
    assert record.status == SyncStatus.PENDING


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately")
def test_record_quote_sent_url_unset_creates_no_record(
    quotation: Quotation, delay_mock: mock.Mock
) -> None:
    """Unset URL = push disabled entirely (dev default) — no SyncRecord."""
    record_quote_sent(quotation, send_path=SEND_PATH_MANUAL)

    assert _records_for(quotation) == []
    delay_mock.assert_not_called()


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately", "delay_mock")
@pytest.mark.parametrize("resend_path", [SEND_PATH_SMTP, SEND_PATH_MANUAL])
def test_resend_of_sent_quote_re_enqueues(quotation: Quotation, resend_path: str) -> None:
    """A re-send IS a send: SENT is editable/re-sendable (renegotiation), and
    the re-send delivers the updated email — the CRM must get the updated
    payload too, not keep the superseded first-send state forever (the record
    is IN_SYNC, so even the sweep could never heal it)."""
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        record_quote_sent(quotation, send_path=SEND_PATH_SMTP)
        (record,) = _records_for(quotation)
        record.status = SyncStatus.IN_SYNC.value
        record.save(update_fields=["status", "updated_at"])

        record_quote_sent(quotation, send_path=resend_path)  # already SENT

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    assert _records_for(quotation) == [record]


@pytest.mark.django_db
@pytest.mark.usefixtures("run_on_commit_immediately")
def test_resend_with_unset_url_stays_noop(quotation: Quotation, delay_mock: mock.Mock) -> None:
    record_quote_sent(quotation, send_path=SEND_PATH_MANUAL)
    record_quote_sent(quotation, send_path=SEND_PATH_MANUAL)  # re-send, still no URL

    assert _records_for(quotation) == []
    delay_mock.assert_not_called()
