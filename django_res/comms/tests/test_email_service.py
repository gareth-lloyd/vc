from __future__ import annotations

import pytest
from django.core import mail

from accounts.models import User
from comms.enums import EmailLogStatus, SmtpScope
from comms.exceptions import EmailTemplateNotFound, NoSmtpProfileAvailable
from comms.models import EmailTemplate, SmtpProfile
from comms.services import EmailService


@pytest.fixture
def system_profile(db: None) -> SmtpProfile:
    return SmtpProfile.objects.create(
        name="System",
        scope=SmtpScope.SYSTEM,
        owner=None,
        host="smtp.example.com",
        port=587,
        username="system",
        encrypted_password="systempw",
        use_tls=True,
        from_email="noreply@example.com",
    )


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(email="agent@example.com", password="pw")


@pytest.fixture
def personal_profile(user: User) -> SmtpProfile:
    return SmtpProfile.objects.create(
        name="Agent Alice",
        scope=SmtpScope.PERSONAL,
        owner=user,
        host="smtp.example.com",
        port=587,
        username="alice",
        encrypted_password="alicepw",
        use_tls=True,
        from_email="alice@example.com",
        reply_to="alice@example.com",
    )


@pytest.fixture
def booking_template(db: None) -> EmailTemplate:
    return EmailTemplate.objects.create(
        key="booking.confirmation",
        version=1,
        subject_template="Booking {{ booking_reference }} confirmed",
        body_template="Hi {{ guest_first_name }}, your stay at {{ property_name }} is booked.",
    )


@pytest.mark.django_db
def test_send_happy_path_renders_and_persists(
    system_profile: SmtpProfile,
    booking_template: EmailTemplate,
) -> None:
    mail.outbox.clear()

    log = EmailService.send(
        template_key="booking.confirmation",
        context={
            "booking_reference": "BK-001",
            "guest_first_name": "Ada",
            "property_name": "Villa Sol",
        },
        to=["guest@example.com"],
        correlation={"booking_id": 1},
    )

    assert log.status == EmailLogStatus.SENT
    assert log.rendered_subject == "Booking BK-001 confirmed"
    assert "Hi Ada, your stay at Villa Sol is booked." in log.rendered_body
    assert log.sent_at is not None
    assert log.smtp_profile == system_profile
    assert log.from_email == system_profile.from_email
    assert log.sender_user is None
    assert log.template_version == 1

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.subject == "Booking BK-001 confirmed"
    assert list(message.to) == ["guest@example.com"]
    assert message.from_email == system_profile.from_email


@pytest.mark.django_db
def test_send_uses_personal_profile_when_available(
    system_profile: SmtpProfile,
    personal_profile: SmtpProfile,
    booking_template: EmailTemplate,
    user: User,
) -> None:
    mail.outbox.clear()

    log = EmailService.send(
        template_key="booking.confirmation",
        context={
            "booking_reference": "BK-002",
            "guest_first_name": "Bo",
            "property_name": "Villa Mar",
        },
        to=["guest@example.com"],
        sender_user=user,
        correlation={"booking_id": 2},
    )

    assert log.smtp_profile == personal_profile
    assert log.from_email == personal_profile.from_email
    assert log.sender_user == user
    assert mail.outbox[-1].from_email == personal_profile.from_email


@pytest.mark.django_db
def test_send_falls_back_to_system_when_no_personal_profile(
    system_profile: SmtpProfile,
    booking_template: EmailTemplate,
    user: User,
) -> None:
    mail.outbox.clear()

    log = EmailService.send(
        template_key="booking.confirmation",
        context={
            "booking_reference": "BK-003",
            "guest_first_name": "Cy",
            "property_name": "Villa Luna",
        },
        to=["guest@example.com"],
        sender_user=user,
        correlation={"booking_id": 3},
    )

    assert log.smtp_profile == system_profile
    assert log.sender_user is None


@pytest.mark.django_db
def test_send_falls_back_when_personal_profile_inactive(
    system_profile: SmtpProfile,
    personal_profile: SmtpProfile,
    booking_template: EmailTemplate,
    user: User,
) -> None:
    personal_profile.is_active = False
    personal_profile.save(update_fields=["is_active"])

    log = EmailService.send(
        template_key="booking.confirmation",
        context={
            "booking_reference": "BK-004",
            "guest_first_name": "Di",
            "property_name": "Villa Stella",
        },
        to=["guest@example.com"],
        sender_user=user,
        correlation={"booking_id": 4},
    )

    assert log.smtp_profile == system_profile


@pytest.mark.django_db
def test_send_idempotent_on_repeat(
    system_profile: SmtpProfile,
    booking_template: EmailTemplate,
) -> None:
    mail.outbox.clear()

    log1 = EmailService.send(
        template_key="booking.confirmation",
        context={
            "booking_reference": "BK-005",
            "guest_first_name": "Eve",
            "property_name": "Villa Cielo",
        },
        to=["guest@example.com", "extra@example.com"],
        correlation={"booking_id": 5},
    )
    log2 = EmailService.send(
        template_key="booking.confirmation",
        context={
            "booking_reference": "BK-005",
            "guest_first_name": "Eve",
            "property_name": "Villa Cielo",
        },
        # Order should not matter for the dedupe.
        to=["extra@example.com", "guest@example.com"],
        correlation={"booking_id": 5},
    )

    assert log1.pk == log2.pk
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_send_raises_when_template_missing(system_profile: SmtpProfile) -> None:
    with pytest.raises(EmailTemplateNotFound):
        EmailService.send(
            template_key="does.not.exist",
            context={},
            to=["guest@example.com"],
        )


@pytest.mark.django_db
def test_send_raises_when_no_system_profile(booking_template: EmailTemplate) -> None:
    with pytest.raises(NoSmtpProfileAvailable):
        EmailService.send(
            template_key="booking.confirmation",
            context={
                "booking_reference": "X",
                "guest_first_name": "Y",
                "property_name": "Z",
            },
            to=["guest@example.com"],
        )


@pytest.mark.django_db
def test_send_does_not_bcc_internal_addresses_by_default(
    system_profile: SmtpProfile,
    booking_template: EmailTemplate,
) -> None:
    mail.outbox.clear()

    log = EmailService.send(
        template_key="booking.confirmation",
        context={
            "booking_reference": "BK-006",
            "guest_first_name": "Fi",
            "property_name": "Villa Nube",
        },
        to=["guest@example.com"],
        correlation={"booking_id": 6},
    )

    assert log.bcc == []
    assert mail.outbox[-1].bcc == []
