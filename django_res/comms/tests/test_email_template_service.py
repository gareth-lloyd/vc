"""Service tests for `EmailTemplateService` — publish + render.

Covers the load-bearing correctness requirements:

- C1: publish render-validates subject / plaintext / compiled HTML (not just
  MJML) and refuses to activate a malformed template, writing nothing.
- C4: publish bumps the version + atomically deactivates the prior active row,
  and a byte-identical re-publish is a no-op (no new version).
- C3: `render` compiles draft MJML on the fly so the preview loop works before
  a draft is ever persisted.
"""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType

from accounts.models import User
from comms.exceptions import MjmlCompileError, TemplatePublishError
from comms.models import EmailTemplate
from comms.services import EmailTemplateService
from core.enums import StaffRole
from core.models import AuditLog

VALID_MJML = (
    "<mjml><mj-body><mj-section><mj-column>"
    "<mj-text>Hi {{ guest_first_name }}</mj-text>"
    "</mj-column></mj-section></mj-body></mjml>"
)

KEY = "test.booking.confirmation"


@pytest.fixture
def actor(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="publisher@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


def _publish(actor: User, **overrides: object) -> EmailTemplate:
    kwargs: dict[str, object] = {
        "key": KEY,
        "subject_template": "Booking {{ booking_reference }} confirmed",
        "body_template": "Hi {{ guest_first_name }}",
        "body_template_mjml": VALID_MJML,
        "notes": "",
        "actor": actor,
    }
    kwargs.update(overrides)
    return EmailTemplateService.publish_version(**kwargs)  # type: ignore[arg-type]


@pytest.mark.django_db
def test_publish_creates_first_active_version(actor: User) -> None:
    template = _publish(actor)

    assert template.version == 1
    assert template.is_active is True
    assert EmailTemplate.objects.filter(key=KEY, is_active=True).count() == 1
    # MJML compiled into the stored HTML via the model's save().
    assert "Hi {{ guest_first_name }}" in template.body_template_html


@pytest.mark.django_db
def test_publish_bumps_version_and_deactivates_prior(actor: User) -> None:
    first = _publish(actor)
    second = _publish(actor, subject_template="Booking {{ booking_reference }} — updated")

    first.refresh_from_db()
    assert second.version == 2
    assert second.is_active is True
    assert first.is_active is False
    # Exactly one active row survives the bump (one_active_template_per_key).
    assert EmailTemplate.objects.filter(key=KEY, is_active=True).count() == 1


@pytest.mark.django_db
def test_publish_records_audit_trail_with_actor(actor: User) -> None:
    _publish(actor)

    content_type = ContentType.objects.get_for_model(EmailTemplate)
    log = (
        AuditLog.objects.filter(content_type=content_type, actor=actor)
        .order_by("-created_at")
        .first()
    )
    assert log is not None
    assert "is_active" in log.field_diffs


@pytest.mark.django_db
def test_publish_byte_identical_is_noop(actor: User) -> None:
    """C4 — a double-clicked Save must not mint a duplicate version."""
    first = _publish(actor)
    again = _publish(actor)

    assert again.pk == first.pk
    assert again.version == 1
    assert EmailTemplate.objects.filter(key=KEY).count() == 1


@pytest.mark.django_db
def test_publish_invalid_subject_tag_raises_and_writes_nothing(actor: User) -> None:
    """C1 — a malformed Django tag in the subject is refused before activation."""
    with pytest.raises(TemplatePublishError):
        _publish(actor, subject_template="Booking {% if %}{{ booking_reference }}")

    assert not EmailTemplate.objects.filter(key=KEY).exists()


@pytest.mark.django_db
def test_publish_invalid_body_tag_leaves_prior_active_row_untouched(actor: User) -> None:
    """C1 — a bad re-publish must not deactivate the working version."""
    first = _publish(actor)

    with pytest.raises(TemplatePublishError):
        _publish(actor, body_template="Hi {% if %}{{ guest_first_name }}")

    first.refresh_from_db()
    assert first.is_active is True
    assert EmailTemplate.objects.filter(key=KEY).count() == 1


@pytest.mark.django_db
def test_publish_invalid_mjml_raises(actor: User) -> None:
    """C1 — broken MJML is refused with the compiler errors."""
    with pytest.raises(TemplatePublishError):
        _publish(actor, body_template_mjml="<not-mjml/>")

    assert not EmailTemplate.objects.filter(key=KEY).exists()


@pytest.mark.django_db
def test_render_active_template_against_context(actor: User) -> None:
    _publish(actor)
    template = EmailTemplate.objects.get(key=KEY, is_active=True)

    rendered = EmailTemplateService.render(
        subject_template=template.subject_template,
        body_template=template.body_template,
        body_template_html=template.body_template_html,
        context={"booking_reference": "VC-100", "guest_first_name": "Ada"},
    )

    assert rendered["rendered_subject"] == "Booking VC-100 confirmed"
    assert rendered["rendered_body_text"] == "Hi Ada"
    assert "Hi Ada" in rendered["rendered_body_html"]


@pytest.mark.django_db
def test_render_draft_compiles_mjml_on_the_fly() -> None:
    """C3 — preview of an unsaved draft has no compiled HTML yet."""
    rendered = EmailTemplateService.render(
        subject_template="Hi {{ guest_first_name }}",
        body_template="Plain {{ guest_first_name }}",
        body_template_mjml=VALID_MJML,
        context={"guest_first_name": "Bo"},
    )

    assert rendered["rendered_subject"] == "Hi Bo"
    assert "Hi Bo" in rendered["rendered_body_html"]


@pytest.mark.django_db
def test_render_draft_invalid_mjml_raises_compile_error() -> None:
    with pytest.raises(MjmlCompileError):
        EmailTemplateService.render(
            subject_template="Hi",
            body_template="Hi",
            body_template_mjml="<not-mjml/>",
            context={},
        )
