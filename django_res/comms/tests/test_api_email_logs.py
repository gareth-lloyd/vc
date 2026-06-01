"""API tests for the top-level `/api/v1/email-logs` surface (GAP-001 slice 1).

A read-only list + detail surface over `EmailLog` for the operator UI's
Comms tab. Unlike `/bookings/{id}/emails` (booking-scoped), this is the
global log. The list serializer omits the rendered body; the detail
serializer includes it.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.enums import StaffRole
from accounts.models import User
from comms.enums import EmailLogStatus
from comms.models import EmailLog, SmtpProfile
from core.tests import assert_max_queries


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        email="logs-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


def _make_log(
    profile: SmtpProfile,
    *,
    subject: str = "Subject",
    body: str = "Body text",
    queued_offset: timedelta = timedelta(),
) -> EmailLog:
    return EmailLog.objects.create(
        template_key="test.key",
        template_version=1,
        to=["guest@example.com"],
        from_email=profile.from_email,
        smtp_profile=profile,
        rendered_subject=subject,
        rendered_body=body,
        status=EmailLogStatus.SENT,
        sent_at=timezone.now(),
        queued_at=timezone.now() - queued_offset,
    )


@pytest.mark.django_db
def test_list_returns_paginated_logs(
    api_client: APIClient,
    staff: User,
    system_profile: SmtpProfile,
) -> None:
    log = _make_log(system_profile, subject="Hello")
    api_client.force_login(staff)

    response = api_client.get("/api/v1/email-logs")

    assert response.status_code == 200
    assert response.data["count"] == 1
    row = response.data["results"][0]
    assert row["id"] == log.pk
    assert row["subject"] == "Hello"
    # List surface omits the rendered body.
    assert "body" not in row


@pytest.mark.django_db
def test_list_orders_newest_first(
    api_client: APIClient,
    staff: User,
    system_profile: SmtpProfile,
) -> None:
    older = _make_log(system_profile, queued_offset=timedelta(hours=2))
    newer = _make_log(system_profile, queued_offset=timedelta(minutes=1))
    api_client.force_login(staff)

    response = api_client.get("/api/v1/email-logs")

    ids = [row["id"] for row in response.data["results"]]
    assert ids == [newer.pk, older.pk]


@pytest.mark.django_db
def test_detail_includes_rendered_body(
    api_client: APIClient,
    staff: User,
    system_profile: SmtpProfile,
) -> None:
    log = _make_log(system_profile, subject="Deposit", body="Hi there")
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/email-logs/{log.pk}")

    assert response.status_code == 200
    assert response.data["id"] == log.pk
    assert response.data["subject"] == "Deposit"
    assert response.data["body"] == "Hi there"


@pytest.mark.django_db
def test_anonymous_is_forbidden(
    api_client: APIClient,
    system_profile: SmtpProfile,
) -> None:
    log = _make_log(system_profile)

    assert api_client.get("/api/v1/email-logs").status_code in (401, 403)
    assert api_client.get(f"/api/v1/email-logs/{log.pk}").status_code in (401, 403)


@pytest.mark.django_db
def test_list_has_no_n_plus_one(
    api_client: APIClient,
    staff: User,
    system_profile: SmtpProfile,
) -> None:
    for _ in range(5):
        _make_log(system_profile)

    api_client.force_login(staff)
    with assert_max_queries(10):
        response = api_client.get("/api/v1/email-logs")
    assert response.status_code == 200
    assert response.data["count"] == 5
