"""API tests for `/bookings/{id}/emails` — list + resend.

The endpoint is wired in `reservations/urls.py` but delegates to
`comms.views.BookingEmailViewSet` (EmailLog isn't linked to Booking via
a FK — the booking_id lives in `EmailLog.correlation`). Tests live in
this app so they can reuse the booking/quotation/property fixture graph
from `reservations/tests/conftest.py`.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from comms.enums import EmailLogStatus, SmtpScope
from comms.models import EmailLog, EmailTemplate, SmtpProfile
from core.enums import StaffRole
from core.tests import assert_max_queries
from pricing.models import Currency, RateRule
from properties.models import Property
from reservations.enums import BookingStatus, PaymentMethod
from reservations.models import Booking, Guest, Quotation, QuotationLine, TermsVersion


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="emails-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="emails-viewer@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


@pytest.fixture
def system_profile(db: None) -> SmtpProfile:
    return SmtpProfile.objects.create(
        name="System",
        scope=SmtpScope.SYSTEM,
        host="smtp.example.com",
        port=587,
        username="system",
        encrypted_password="systempw",
        use_tls=True,
        from_email="noreply@example.com",
    )


@pytest.fixture
def template(db: None) -> EmailTemplate:
    return EmailTemplate.objects.create(
        key="test.booking.deposit_request",
        version=1,
        subject_template="Deposit for {{ booking_reference }}",
        title="Hi {{ guest_first_name }}",
    )


@pytest.fixture
def booking(
    db: None,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> Booking:
    quotation = Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        property=property_,
        date_from=line.date_from,
        date_to=line.date_to,
        adults=line.adults,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )


@pytest.fixture
def booking_email(
    booking: Booking,
    template: EmailTemplate,
    system_profile: SmtpProfile,
) -> EmailLog:
    return EmailLog.objects.create(
        template_key=template.key,
        template_version=template.version,
        to=["guest@example.com"],
        from_email=system_profile.from_email,
        smtp_profile=system_profile,
        rendered_subject=f"Deposit for {booking.reference}",
        rendered_body=f"Hi {booking.guest.first_name}",
        status=EmailLogStatus.SENT,
        sent_at=timezone.now(),
        correlation={"booking_id": booking.pk},
    )


@pytest.fixture
def other_booking_email(
    template: EmailTemplate,
    system_profile: SmtpProfile,
) -> EmailLog:
    """An EmailLog correlated to a *different* booking — must not leak."""
    return EmailLog.objects.create(
        template_key=template.key,
        template_version=template.version,
        to=["other@example.com"],
        from_email=system_profile.from_email,
        smtp_profile=system_profile,
        rendered_subject="Other booking",
        rendered_body="...",
        status=EmailLogStatus.SENT,
        sent_at=timezone.now(),
        correlation={"booking_id": 99_999},
    )


@pytest.mark.django_db
def test_list_returns_only_emails_for_this_booking(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    booking_email: EmailLog,
    other_booking_email: EmailLog,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}/emails")

    assert response.status_code == 200
    assert response.data["count"] == 1
    row = response.data["results"][0]
    assert row["id"] == booking_email.pk
    assert row["subject"] == booking_email.rendered_subject
    assert row["to"] == ["guest@example.com"]
    assert row["status"] == EmailLogStatus.SENT.value
    assert row["template_key"] == "test.booking.deposit_request"


@pytest.mark.django_db
def test_list_orders_newest_first(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    template: EmailTemplate,
    system_profile: SmtpProfile,
) -> None:
    older = EmailLog.objects.create(
        template_key=template.key,
        template_version=template.version,
        to=["g@example.com"],
        from_email=system_profile.from_email,
        smtp_profile=system_profile,
        rendered_subject="Older",
        rendered_body="...",
        status=EmailLogStatus.SENT,
        correlation={"booking_id": booking.pk},
        queued_at=timezone.now() - timedelta(hours=2),
    )
    newer = EmailLog.objects.create(
        template_key=template.key,
        template_version=template.version,
        to=["g@example.com"],
        from_email=system_profile.from_email,
        smtp_profile=system_profile,
        rendered_subject="Newer",
        rendered_body="...",
        status=EmailLogStatus.SENT,
        correlation={"booking_id": booking.pk},
        queued_at=timezone.now() - timedelta(minutes=5),
    )

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}/emails")

    ids = [row["id"] for row in response.data["results"]]
    assert ids == [newer.pk, older.pk]


@pytest.mark.django_db
def test_list_anonymous_is_forbidden(
    api_client: APIClient,
    booking: Booking,
    booking_email: EmailLog,
) -> None:
    response = api_client.get(f"/api/v1/bookings/{booking.pk}/emails")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_list_has_no_n_plus_one(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    template: EmailTemplate,
    system_profile: SmtpProfile,
) -> None:
    """Pin query count: list of 1 email and list of 5 emails must match."""
    for i in range(5):
        EmailLog.objects.create(
            template_key=template.key,
            template_version=template.version,
            to=[f"g{i}@example.com"],
            from_email=system_profile.from_email,
            smtp_profile=system_profile,
            rendered_subject=f"Email {i}",
            rendered_body="...",
            status=EmailLogStatus.SENT,
            correlation={"booking_id": booking.pk},
        )

    api_client.force_login(staff)
    with assert_max_queries(10):
        response = api_client.get(f"/api/v1/bookings/{booking.pk}/emails")
    assert response.status_code == 200
    assert response.data["count"] == 5


@pytest.mark.django_db
def test_resend_creates_new_log_and_dispatches(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    booking_email: EmailLog,
    django_capture_on_commit_callbacks: Any,
) -> None:
    mail.outbox.clear()
    api_client.force_login(staff)

    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            f"/api/v1/bookings/{booking.pk}/emails/{booking_email.pk}:resend",
            data={"idempotency_key": "abc-123"},
            format="json",
        )

    assert response.status_code == 201
    new_id = response.data["id"]
    assert new_id != booking_email.pk

    new_log = EmailLog.objects.get(pk=new_id)
    assert new_log.correlation["booking_id"] == booking.pk
    assert new_log.correlation["resent_from"] == booking_email.pk
    assert new_log.correlation["resend_token"] == "abc-123"
    assert new_log.rendered_subject == booking_email.rendered_subject
    assert new_log.to == booking_email.to
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_resend_is_idempotent_on_repeat_token(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    booking_email: EmailLog,
    django_capture_on_commit_callbacks: Any,
) -> None:
    mail.outbox.clear()
    api_client.force_login(staff)

    with django_capture_on_commit_callbacks(execute=True):
        first = api_client.post(
            f"/api/v1/bookings/{booking.pk}/emails/{booking_email.pk}:resend",
            data={"idempotency_key": "same-token"},
            format="json",
        )
    with django_capture_on_commit_callbacks(execute=True):
        second = api_client.post(
            f"/api/v1/bookings/{booking.pk}/emails/{booking_email.pk}:resend",
            data={"idempotency_key": "same-token"},
            format="json",
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.data["id"] == second.data["id"]
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_resend_without_token_creates_fresh_row_each_time(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    booking_email: EmailLog,
    django_capture_on_commit_callbacks: Any,
) -> None:
    mail.outbox.clear()
    api_client.force_login(staff)

    with django_capture_on_commit_callbacks(execute=True):
        first = api_client.post(
            f"/api/v1/bookings/{booking.pk}/emails/{booking_email.pk}:resend",
            format="json",
        )
    with django_capture_on_commit_callbacks(execute=True):
        second = api_client.post(
            f"/api/v1/bookings/{booking.pk}/emails/{booking_email.pk}:resend",
            format="json",
        )

    assert first.data["id"] != second.data["id"]
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_resend_clones_original_sender_profile_and_from_email(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    booking_email: EmailLog,
    django_capture_on_commit_callbacks: Any,
) -> None:
    """Resend must clone the original SmtpProfile + from_email so the
    guest sees a consistent sender across attempts — not rewrite to the
    operator's personal profile.
    """
    SmtpProfile.objects.create(
        name=f"Personal-{staff.email}",
        scope=SmtpScope.PERSONAL,
        owner=staff,
        host="smtp.personal.example.com",
        port=587,
        username="personal",
        encrypted_password="pw",
        use_tls=True,
        from_email="agent@example.com",
    )
    api_client.force_login(staff)

    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            f"/api/v1/bookings/{booking.pk}/emails/{booking_email.pk}:resend",
            format="json",
        )

    assert response.status_code == 201
    new_log = EmailLog.objects.get(pk=response.data["id"])
    assert new_log.smtp_profile_id == booking_email.smtp_profile_id
    assert new_log.from_email == booking_email.from_email


@pytest.mark.django_db
def test_resend_falls_back_to_system_when_original_profile_deactivated(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    template: EmailTemplate,
    system_profile: SmtpProfile,
    django_capture_on_commit_callbacks: Any,
) -> None:
    """If the original SmtpProfile has been deactivated since the first
    send, fall back to the system profile rather than the operator's.
    """
    former_owner = User.objects.create_user(
        is_staff=True,
        email="former-agent@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )
    deactivated = SmtpProfile.objects.create(
        name="Old-Personal",
        scope=SmtpScope.PERSONAL,
        owner=former_owner,
        host="smtp.old.example.com",
        port=587,
        username="old",
        encrypted_password="pw",
        use_tls=True,
        from_email="old-agent@example.com",
        is_active=False,
    )
    original = EmailLog.objects.create(
        template_key=template.key,
        template_version=template.version,
        to=["guest@example.com"],
        from_email=deactivated.from_email,
        smtp_profile=deactivated,
        rendered_subject="Old subject",
        rendered_body="...",
        status=EmailLogStatus.SENT,
        sent_at=timezone.now(),
        correlation={"booking_id": booking.pk},
    )
    SmtpProfile.objects.create(
        name=f"Personal-{staff.email}",
        scope=SmtpScope.PERSONAL,
        owner=staff,
        host="smtp.personal.example.com",
        port=587,
        username="personal",
        encrypted_password="pw",
        use_tls=True,
        from_email="agent@example.com",
    )

    api_client.force_login(staff)
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            f"/api/v1/bookings/{booking.pk}/emails/{original.pk}:resend",
            format="json",
        )

    assert response.status_code == 201
    new_log = EmailLog.objects.get(pk=response.data["id"])
    assert new_log.smtp_profile_id == system_profile.pk
    assert new_log.from_email == system_profile.from_email


@pytest.mark.django_db
def test_resend_for_email_on_different_booking_404s(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    other_booking_email: EmailLog,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/emails/{other_booking_email.pk}:resend",
        format="json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_resend_requires_reservations_role(
    api_client: APIClient,
    viewer: User,
    booking: Booking,
    booking_email: EmailLog,
) -> None:
    api_client.force_login(viewer)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/emails/{booking_email.pk}:resend",
        format="json",
    )
    assert response.status_code == 403
