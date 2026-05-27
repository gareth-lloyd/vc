"""Tests for the two send paths: in-app SMTP send + manual-mark.

T3.3 — per `workflows/08-quotation/transmission.md` "Django redesign — two send paths".

Both paths must produce the same downstream state writes:
- `Quotation.status = SENT`
- `Enquiry.status = QUOTED`
- Zoho push queued (PENDING `SyncRecord`)
- `EnquiryEvent(kind=QUOTE_SENT, meta={"send_path": ...})`

The SMTP path additionally creates an `EmailLog`; the manual path must not.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.enums import StaffRole
from accounts.models import User
from comms.models import EmailLog
from integrations.enums import SyncProvider, SyncStatus
from integrations.models import SyncRecord
from reservations.enums import (
    EnquiryEventKind,
    EnquiryStatus,
    QuotationStatus,
)
from reservations.models import (
    Enquiry,
    EnquiryEvent,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)

if TYPE_CHECKING:
    from pricing.models import Currency
    from properties.models import Property


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        email="quote-mark-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        email="quote-mark-viewer@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


@pytest.fixture
def enquiry(guest: Guest) -> Enquiry:
    return Enquiry.objects.create(
        guest=guest,
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        adults=2,
    )


@pytest.fixture
def quotation(
    enquiry: Enquiry,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
) -> Quotation:
    return Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )


@pytest.fixture
def line(quotation: Quotation, property_: Property) -> QuotationLine:
    return QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )


@pytest.fixture
def lifecycle_templates(db: None) -> None:
    """Seed email templates so the SMTP-path signal handler can dispatch."""
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates()


def _quote_sent_events(quotation: Quotation) -> list[EnquiryEvent]:
    assert quotation.enquiry is not None
    return list(
        EnquiryEvent.objects.filter(
            enquiry=quotation.enquiry,
            kind=EnquiryEventKind.QUOTE_SENT.value,
        ).order_by("created_at")
    )


def _zoho_sync_records(quotation: Quotation) -> list[SyncRecord]:
    ct = ContentType.objects.get_for_model(Quotation)
    return list(
        SyncRecord.objects.filter(
            content_type=ct,
            object_id=quotation.pk,
            provider=SyncProvider.ZOHO_CRM.value,
        )
    )


# ----------------------------------------------------------------------
# Manual-mark endpoint
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_manual_mark_creates_no_email_log(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
) -> None:
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/quotations/{quotation.pk}:mark-manually-sent")

    assert response.status_code == 200, response.data
    assert EmailLog.objects.filter(correlation__quotation_id=quotation.pk).count() == 0


@pytest.mark.django_db
def test_manual_mark_flips_quotation_and_enquiry_status(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    enquiry: Enquiry,
) -> None:
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/quotations/{quotation.pk}:mark-manually-sent")

    assert response.status_code == 200, response.data
    quotation.refresh_from_db()
    enquiry.refresh_from_db()
    assert quotation.status == QuotationStatus.SENT.value
    assert enquiry.status == EnquiryStatus.QUOTED.value


@pytest.mark.django_db
def test_manual_mark_queues_zoho_push(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
) -> None:
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/quotations/{quotation.pk}:mark-manually-sent")

    assert response.status_code == 200, response.data
    records = _zoho_sync_records(quotation)
    assert len(records) == 1
    assert records[0].status == SyncStatus.PENDING.value


@pytest.mark.django_db
def test_manual_mark_writes_event_with_send_path_manual(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
) -> None:
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/quotations/{quotation.pk}:mark-manually-sent")

    assert response.status_code == 200, response.data
    events = _quote_sent_events(quotation)
    assert len(events) == 1
    assert events[0].meta.get("send_path") == "manual"
    assert events[0].meta.get("quotation_id") == quotation.pk


@pytest.mark.django_db
def test_manual_mark_idempotent(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
) -> None:
    api_client.force_login(staff)

    first = api_client.post(f"/api/v1/quotations/{quotation.pk}:mark-manually-sent")
    assert first.status_code == 200, first.data

    # Capture state after the first call.
    events_after_first = _quote_sent_events(quotation)
    records_after_first = _zoho_sync_records(quotation)

    second = api_client.post(f"/api/v1/quotations/{quotation.pk}:mark-manually-sent")
    assert second.status_code == 200, second.data

    # No additional side effects on the second call.
    events_after_second = _quote_sent_events(quotation)
    records_after_second = _zoho_sync_records(quotation)
    assert len(events_after_second) == len(events_after_first)
    assert len(records_after_second) == len(records_after_first)


@pytest.mark.django_db
def test_manual_mark_requires_send_permission(
    api_client: APIClient,
    viewer: User,
    quotation: Quotation,
) -> None:
    api_client.force_login(viewer)

    response = api_client.post(f"/api/v1/quotations/{quotation.pk}:mark-manually-sent")

    assert response.status_code == 403
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.DRAFT.value


# ----------------------------------------------------------------------
# SMTP path regression — must also write the EnquiryEvent with send_path
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_smtp_send_writes_event_with_send_path_smtp(
    api_client: APIClient,
    staff: User,
    quotation: Quotation,
    lifecycle_templates: None,
) -> None:
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/quotations/{quotation.pk}:send")

    assert response.status_code == 200, response.data
    events = _quote_sent_events(quotation)
    # Exactly one QUOTE_SENT event with send_path="smtp" must exist.
    smtp_events = [e for e in events if e.meta.get("send_path") == "smtp"]
    assert len(smtp_events) == 1
    assert smtp_events[0].meta.get("quotation_id") == quotation.pk
