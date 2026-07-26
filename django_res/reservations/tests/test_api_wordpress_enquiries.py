"""POST /api/wordpress/enquiries — token-authed WP inbound enquiry endpoint.

Design: 08-integrations.md §"Inbound: WordPress → Django" (fork C): DRF
TokenAuthentication + service-user email pin + scoped throttle + the
IntegrationInboundCall record-or-replay ledger keyed by the server-derived
payload hash. Clean 201 `{"reference": "E…"}` envelope.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
import time_machine
from django.contrib.contenttypes.models import ContentType
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from accounts.factories import UserFactory
from accounts.models import User
from core.models import AuditLog
from integrations.enums import SyncProvider
from integrations.management.commands.bootstrap_wordpress_user import (
    ensure_wordpress_service_user,
)
from integrations.models import IntegrationInboundCall, SyncRecord
from reservations.models import Enquiry

pytestmark = pytest.mark.django_db

_URL = "/api/wordpress/enquiries"

_PAYLOAD: dict[str, Any] = {
    "FirstName": "Pat",
    "LastName": "Example",
    "Email": "pat@example.com",
    "CountryCode": "+44",
    "ContactNo": "07911123456",
    "Properties": "0",
    "RegionIds": ["0"],
    "FromDate": "2026-08-15",
    "ToDate": "2026-08-29",
    "EnquireDateType": 7,
    "EnquireDateTypeString": "Specific dates",
    "CountryIds": "1",
    "MinBed": "5",
    "MaxBed": "0",
    "Adults": "7",
    "Children": "1",
    "Notes": "Looking for a villa with a pool.",
    "referral": "",
    "UserFeedback": "Google/Online Search",
    "other_text": "Other",
    "IsSignUp": True,
}


@pytest.fixture()
def wp_client() -> APIClient:
    _, token, _ = ensure_wordpress_service_user()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def test_unauthenticated_post_is_401() -> None:
    response = APIClient().post(_URL, _PAYLOAD, format="json")

    assert response.status_code == 401
    assert Enquiry.objects.count() == 0


def test_another_users_token_is_403() -> None:
    other = cast(User, UserFactory())
    token = Token.objects.create(user=other)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    response = client.post(_URL, _PAYLOAD, format="json")

    assert response.status_code == 403
    assert Enquiry.objects.count() == 0


def test_staff_session_is_not_accepted() -> None:
    # SessionAuthentication is deliberately absent from this view — a staff
    # browser session must not be able to drive the WP intake surface.
    staff = cast(User, UserFactory(is_staff=True))
    client = APIClient()
    client.force_login(staff)

    response = client.post(_URL, _PAYLOAD, format="json")

    assert response.status_code == 401


def test_blank_service_email_setting_fails_closed(wp_client: APIClient, settings: Any) -> None:
    # A user with an empty email + any token must never slip through the pin
    # if the setting is accidentally blanked.
    settings.WORDPRESS_SERVICE_EMAIL = ""
    blank_user = User.objects.create(email="")
    token = Token.objects.create(user=blank_user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    assert client.post(_URL, _PAYLOAD, format="json").status_code == 403
    assert wp_client.post(_URL, _PAYLOAD, format="json").status_code == 403


@time_machine.travel("2026-07-26 14:10:00 +0000")
def test_volatile_undeclared_keys_cannot_defeat_dedupe(wp_client: APIClient) -> None:
    # The idempotency key hashes the VALIDATED payload, so keys the serializer
    # ignores (nonces, timestamps) don't turn a retry into a duplicate lead.
    first = wp_client.post(_URL, {**_PAYLOAD, "nonce": "a1"}, format="json")
    second = wp_client.post(_URL, {**_PAYLOAD, "nonce": "b2"}, format="json")

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert Enquiry.objects.count() == 1


def test_valid_post_creates_enquiry_and_returns_reference(wp_client: APIClient) -> None:
    response = wp_client.post(_URL, _PAYLOAD, format="json")

    assert response.status_code == 201
    enquiry = Enquiry.objects.get()
    assert response.json() == {"reference": enquiry.reference}
    assert enquiry.email == "pat@example.com"
    assert enquiry.is_flexible is False


@time_machine.travel("2026-07-26 14:10:00 +0000")
def test_repeat_payload_replays_without_a_duplicate_lead(wp_client: APIClient) -> None:
    first = wp_client.post(_URL, _PAYLOAD, format="json")
    second = wp_client.post(_URL, _PAYLOAD, format="json")

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()
    assert Enquiry.objects.count() == 1
    assert IntegrationInboundCall.objects.count() == 1


def test_invalid_types_are_rejected_and_nothing_recorded(wp_client: APIClient) -> None:
    response = wp_client.post(_URL, {"FromDate": "not-a-date"}, format="json")

    assert response.status_code == 400
    assert Enquiry.objects.count() == 0
    assert IntegrationInboundCall.objects.count() == 0


def test_trailing_slash_variant_404s(wp_client: APIClient) -> None:
    # Router convention is trailing_slash=False; APPEND_SLASH can't redirect
    # a POST, so the wrong variant must 404 loudly, not silently work.
    response = wp_client.post(_URL + "/", _PAYLOAD, format="json")

    assert response.status_code == 404


def test_zoho_sync_record_is_created_when_webhook_configured(
    wp_client: APIClient, settings: Any
) -> None:
    settings.ZOHO_FLOW_WEBHOOKS = {**settings.ZOHO_FLOW_WEBHOOKS, "enquiry": "https://flow.test/x"}

    response = wp_client.post(_URL, _PAYLOAD, format="json")

    assert response.status_code == 201
    enquiry = Enquiry.objects.get()
    assert SyncRecord.objects.filter(
        provider=SyncProvider.ZOHO_CRM,
        content_type=ContentType.objects.get_for_model(Enquiry),
        object_id=enquiry.pk,
    ).exists()


@time_machine.travel("2026-07-26 14:10:00 +0000")
def test_every_handled_call_writes_an_audit_row(wp_client: APIClient) -> None:
    wp_client.post(_URL, _PAYLOAD, format="json")
    wp_client.post(_URL, _PAYLOAD, format="json")  # replay

    call = IntegrationInboundCall.objects.get()
    rows = AuditLog.objects.filter(
        content_type=ContentType.objects.get_for_model(IntegrationInboundCall),
        object_id=str(call.pk),
    ).order_by("created_at")
    assert rows.count() == 2
    assert [r.field_diffs["replayed"][1] for r in rows] == [False, True]
    service_user_pk = ensure_wordpress_service_user()[0].pk
    assert {r.actor_id for r in rows} == {service_user_pk}


def test_scoped_throttle_kicks_in(wp_client: APIClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from django.core.cache import cache

    cache.clear()
    monkeypatch.setattr(SimpleRateThrottle, "THROTTLE_RATES", {"wordpress_inbound": "2/min"})

    codes = [
        wp_client.post(_URL, {**_PAYLOAD, "Notes": f"n{i}"}, format="json").status_code
        for i in range(3)
    ]

    assert codes[:2] == [201, 201]
    assert codes[2] == 429
