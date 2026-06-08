"""API tests for the `/api/v1/email-templates/*` admin surface.

Covers the correctness requirements end-to-end:

- C2: dotted keys (`booking.confirmation`) route to the detail endpoint.
- C1: publishing a malformed template returns 400 carrying the errors.
- C3: previewing draft MJML compiles on the fly; a broken draft is 400, not 500.
- C5: test-sends never tag a booking, and each one logs a fresh row.

Authz: reads (incl. preview) open to any staff; publish + test-send gated to
ADMIN / RESERVATIONS.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from comms.models import EmailLog, EmailTemplate, SmtpProfile
from core.enums import StaffRole
from core.tests import assert_max_queries

# A dotted key (exercises C2 routing) that won't collide with the real
# catalogue the test DB pre-seeds (`booking.confirmation` et al already exist).
KEY = "test.booking.confirmation"

VALID_MJML = (
    "<mjml><mj-body><mj-section><mj-column>"
    "<mj-text>Hi {{ guest_first_name }}</mj-text>"
    "</mj-column></mj-section></mj-body></mjml>"
)


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def reservations(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="tmpl-res@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="tmpl-viewer@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


@pytest.fixture
def active_template(db: None) -> EmailTemplate:
    return EmailTemplate.objects.create(
        key=KEY,
        title="Booking Confirmation",
        version=1,
        subject_template="Booking {{ booking_reference }} confirmed",
        body_template_mjml=VALID_MJML,
    )


# --- routing + reads ------------------------------------------------------


@pytest.mark.django_db
def test_dotted_key_retrieves_active_version(
    api_client: APIClient, reservations: User, active_template: EmailTemplate
) -> None:
    """C2 — a dotted key resolves rather than being split on the dot."""
    api_client.force_login(reservations)

    response = api_client.get(f"/api/v1/email-templates/{KEY}")

    assert response.status_code == 200
    assert response.data["key"] == KEY
    assert response.data["title"] == "Booking Confirmation"
    assert response.data["version"] == 1
    assert response.data["subject_template"] == "Booking {{ booking_reference }} confirmed"


@pytest.mark.django_db
def test_list_omits_bodies(
    api_client: APIClient, reservations: User, active_template: EmailTemplate
) -> None:
    api_client.force_login(reservations)

    response = api_client.get(f"/api/v1/email-templates?key={KEY}")

    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["key"] == KEY
    # The human-facing title is in the catalogue row.
    assert row["title"] == "Booking Confirmation"
    # The catalogue row carries identity + provenance only — no bodies.
    assert "subject_template" not in row


@pytest.mark.django_db
def test_list_is_query_bounded(
    api_client: APIClient, reservations: User, active_template: EmailTemplate
) -> None:
    EmailTemplate.objects.create(
        key="test.payment.receipt", title="Payment Receipt", version=1, subject_template="s"
    )
    api_client.force_login(reservations)

    with assert_max_queries(10):
        response = api_client.get("/api/v1/email-templates")
    assert response.status_code == 200


@pytest.mark.django_db
def test_anonymous_is_rejected(api_client: APIClient, active_template: EmailTemplate) -> None:
    assert api_client.get(f"/api/v1/email-templates/{KEY}").status_code in (401, 403)


# --- publish (PUT) --------------------------------------------------------


@pytest.mark.django_db
def test_reservations_can_publish_new_version(
    api_client: APIClient, reservations: User, active_template: EmailTemplate
) -> None:
    api_client.force_login(reservations)

    response = api_client.put(
        f"/api/v1/email-templates/{KEY}",
        {
            "title": "Booking Confirmation",
            "subject_template": "Booking {{ booking_reference }} — confirmed!",
            "body_template_mjml": VALID_MJML,
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["version"] == 2
    assert EmailTemplate.objects.filter(key=KEY, is_active=True).count() == 1


@pytest.mark.django_db
def test_publish_creates_brand_new_key(api_client: APIClient, reservations: User) -> None:
    api_client.force_login(reservations)

    response = api_client.put(
        "/api/v1/email-templates/test.brand.new",
        {
            "title": "Approval Request",
            "subject_template": "Approve {{ booking_reference }}",
            "body_template_mjml": VALID_MJML,
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["version"] == 1
    assert EmailTemplate.objects.filter(key="test.brand.new", is_active=True).exists()


@pytest.mark.django_db
def test_viewer_cannot_publish(
    api_client: APIClient, viewer: User, active_template: EmailTemplate
) -> None:
    api_client.force_login(viewer)

    response = api_client.put(
        f"/api/v1/email-templates/{KEY}",
        {"title": "x", "subject_template": "x", "body_template_mjml": VALID_MJML},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_publish_malformed_template_returns_400_with_errors(
    api_client: APIClient, reservations: User, active_template: EmailTemplate
) -> None:
    """C1 — a malformed Django tag is refused; the working version survives."""
    api_client.force_login(reservations)

    response = api_client.put(
        f"/api/v1/email-templates/{KEY}",
        {
            "title": "Booking Confirmation",
            "subject_template": "Bad {% if %}",
            "body_template_mjml": VALID_MJML,
        },
        format="json",
    )

    assert response.status_code == 400
    # Canonical error shape — per-field messages, not a bespoke `errors` key.
    assert response.data["field_errors"]
    # Prior active version untouched.
    assert EmailTemplate.objects.filter(key=KEY).count() == 1
    assert EmailTemplate.objects.get(key=KEY).version == 1


@pytest.mark.django_db
def test_publish_requires_title(
    api_client: APIClient, reservations: User, active_template: EmailTemplate
) -> None:
    api_client.force_login(reservations)

    response = api_client.put(
        f"/api/v1/email-templates/{KEY}",
        {"subject_template": "s", "body_template_mjml": VALID_MJML},
        format="json",
    )

    assert response.status_code == 400
    assert "title" in response.data["field_errors"]


@pytest.mark.django_db
def test_publish_requires_mjml_body(
    api_client: APIClient, reservations: User, active_template: EmailTemplate
) -> None:
    """The MJML body is the only authored body source, so it's required."""
    api_client.force_login(reservations)

    response = api_client.put(
        f"/api/v1/email-templates/{KEY}",
        {"title": "Booking Confirmation", "subject_template": "s"},
        format="json",
    )

    assert response.status_code == 400
    assert "body_template_mjml" in response.data["field_errors"]


# --- preview --------------------------------------------------------------


@pytest.mark.django_db
def test_preview_renders_against_explicit_context(
    api_client: APIClient, viewer: User, active_template: EmailTemplate
) -> None:
    """VIEWER can preview (per-action read perm); explicit context wins."""
    api_client.force_login(viewer)

    response = api_client.post(
        f"/api/v1/email-templates/{KEY}/preview",
        {"context": {"booking_reference": "VC-9", "guest_first_name": "Ada"}},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["rendered_subject"] == "Booking VC-9 confirmed"
    assert "Hi Ada" in response.data["rendered_body_html"]
    # Preview writes no log.
    assert not EmailLog.objects.exists()


@pytest.mark.django_db
def test_preview_compiles_draft_mjml(
    api_client: APIClient, reservations: User, active_template: EmailTemplate
) -> None:
    """C3 — draft override MJML compiles on the fly."""
    api_client.force_login(reservations)
    draft = VALID_MJML.replace("Hi {{ guest_first_name }}", "DRAFT {{ guest_first_name }}")

    response = api_client.post(
        f"/api/v1/email-templates/{KEY}/preview",
        {
            "body_template_mjml": draft,
            "context": {"guest_first_name": "Bo"},
        },
        format="json",
    )

    assert response.status_code == 200
    assert "DRAFT Bo" in response.data["rendered_body_html"]


@pytest.mark.django_db
def test_preview_invalid_draft_mjml_is_400(
    api_client: APIClient, reservations: User, active_template: EmailTemplate
) -> None:
    """C3 — a broken draft is a 400, never a 500."""
    api_client.force_login(reservations)

    response = api_client.post(
        f"/api/v1/email-templates/{KEY}/preview",
        {"body_template_mjml": "<not-mjml/>", "context": {}},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["field_errors"]


# --- test-send ------------------------------------------------------------


@pytest.mark.django_db
def test_test_send_writes_fresh_log_untagged(
    api_client: APIClient,
    reservations: User,
    active_template: EmailTemplate,
    system_profile: SmtpProfile,
) -> None:
    """C5 — each test-send logs a fresh row tagged test_send, never a booking."""
    api_client.force_login(reservations)
    payload = {"to": "qa@example.com", "context": {"guest_first_name": "Ada"}}

    first = api_client.post(f"/api/v1/email-templates/{KEY}/test-send", payload, format="json")
    second = api_client.post(f"/api/v1/email-templates/{KEY}/test-send", payload, format="json")

    assert first.status_code == 201
    assert second.status_code == 201
    # Two distinct rows — the nonce defeats send dedup.
    assert first.data["id"] != second.data["id"]
    logs = EmailLog.objects.filter(template_key=KEY)
    assert logs.count() == 2
    for log in logs:
        assert log.correlation.get("test_send") is True
        assert "booking_id" not in log.correlation
    # A per-booking Comms-tab query must not surface a test-send.
    assert not EmailLog.objects.filter(correlation__booking_id__isnull=False).exists()


@pytest.mark.django_db
def test_viewer_cannot_test_send(
    api_client: APIClient,
    viewer: User,
    active_template: EmailTemplate,
    system_profile: SmtpProfile,
) -> None:
    api_client.force_login(viewer)

    response = api_client.post(
        f"/api/v1/email-templates/{KEY}/test-send",
        {"to": "qa@example.com"},
        format="json",
    )

    assert response.status_code == 403


# --- version history ------------------------------------------------------


@pytest.mark.django_db
def test_versions_list_and_detail(
    api_client: APIClient, reservations: User, active_template: EmailTemplate
) -> None:
    api_client.force_login(reservations)
    # Publish a v2 so there's history.
    api_client.put(
        f"/api/v1/email-templates/{KEY}",
        {
            "title": "Booking Confirmation",
            "subject_template": "v2 {{ booking_reference }}",
            "body_template_mjml": VALID_MJML,
        },
        format="json",
    )

    listing = api_client.get(f"/api/v1/email-templates/{KEY}/versions")
    assert listing.status_code == 200
    versions = [row["version"] for row in listing.data]
    assert versions == [2, 1]  # newest first

    detail = api_client.get(f"/api/v1/email-templates/{KEY}/versions/1")
    assert detail.status_code == 200
    assert detail.data["version"] == 1
    assert detail.data["is_active"] is False
