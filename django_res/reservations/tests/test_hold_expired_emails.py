"""Round-trip tests for the `hold.expired` lifecycle email.

Drives `reservations.tasks.expire_holds()` which fires `hold_expired`
once per released row. The `comms.signals.hold_expired_handler` notifies
the agent on the underlying quotation; operator and maintenance holds
(no quotation/no agent user/no agent email) are silently skipped.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from accounts.models import Contact, User
from comms.models import EmailLog
from reservations.enums import BookingHoldReason
from reservations.models.booking import BookingHold
from reservations.tasks import expire_holds

if TYPE_CHECKING:
    from comms.models import SmtpProfile
    from properties.models import Property
    from reservations.models import Quotation, QuotationLine


@pytest.fixture
def lifecycle_templates(db: None) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates()


def _make_expired_hold(
    *,
    property_: Property,
    reason: str,
    quotation: Quotation | None = None,
    offset_days: int = 30,
) -> BookingHold:
    """Create a hold that is already past `expires_at`.

    `reason` is required because the `bookinghold_has_source_or_blocking_reason`
    CHECK constraint rejects a hold with no quotation/booking unless `reason`
    is one of the blocking values (OWNER_BLOCK / MAINTENANCE / MANUAL).

    `offset_days` shifts the (7-day) stay window so two holds on the same
    property can coexist without tripping the no-overlap constraint.
    """
    now = timezone.now()
    return BookingHold.objects.create(
        property=property_,
        quotation=quotation,
        date_from=date.today() + timedelta(days=offset_days),
        date_to=date.today() + timedelta(days=offset_days + 7),
        expires_at=now - timedelta(minutes=1),
        reason=reason,
    )


def _logs_for_hold(hold: BookingHold) -> list[EmailLog]:
    return list(
        EmailLog.objects.filter(
            template_key="hold.expired",
            correlation__hold_id=hold.pk,
        )
    )


@pytest.mark.django_db
def test_expire_holds_notifies_agent_for_quotation_hold(
    quotation_line: QuotationLine,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    agent_user = User.objects.create_user(
        email="agent-hold@example.com",
        password="agent-pw",
        first_name="Aaron",
        last_name="Agent",
    )
    agent_contact = Contact.objects.create(
        first_name="Aaron",
        last_name="Agent",
        user=agent_user,
    )
    quotation = quotation_line.quotation
    quotation.agent = agent_contact
    quotation.save(update_fields=["agent", "updated_at"])

    hold = _make_expired_hold(
        property_=quotation_line.property,
        quotation=quotation,
        reason=BookingHoldReason.QUOTATION_OPEN.value,
    )
    # An expired operator block on the same property (non-overlapping dates).
    # A single expire_holds() call must release both disparate holds together
    # while only the agent-bearing quotation hold yields an email.
    operator_block = _make_expired_hold(
        property_=quotation_line.property,
        quotation=None,
        reason=BookingHoldReason.OWNER_BLOCK.value,
        offset_days=60,
    )

    released_ids = expire_holds()

    assert set(released_ids) == {hold.pk, operator_block.pk}
    logs = _logs_for_hold(hold)
    assert len(logs) == 1
    log = logs[0]
    assert log.to == [agent_user.email]
    assert log.correlation == {
        "quotation_id": quotation.pk,
        "hold_id": hold.pk,
    }
    # The operator block has no agent and must not yield an email.
    assert _logs_for_hold(operator_block) == []


@pytest.mark.django_db
def test_expire_holds_skips_operator_hold_with_no_quotation(
    property_: Property,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    hold = _make_expired_hold(
        property_=property_,
        quotation=None,
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )

    released_ids = expire_holds()

    assert released_ids == [hold.pk]
    assert _logs_for_hold(hold) == []


@pytest.mark.django_db
def test_expire_holds_skips_when_agent_contact_has_no_user(
    quotation_line: QuotationLine,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    agent_contact = Contact.objects.create(
        first_name="Bea",
        last_name="Agent",
        # No linked user.
    )
    quotation = quotation_line.quotation
    quotation.agent = agent_contact
    quotation.save(update_fields=["agent", "updated_at"])

    hold = _make_expired_hold(
        property_=quotation_line.property,
        quotation=quotation,
        reason=BookingHoldReason.QUOTATION_OPEN.value,
    )

    expire_holds()

    assert _logs_for_hold(hold) == []


@pytest.mark.django_db
def test_expire_holds_skips_when_agent_user_has_no_email(
    quotation_line: QuotationLine,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    agent_user = User.objects.create_user(
        email="agent-empty@example.com",
        password="agent-pw",
    )
    # Strip the email after creation — create_user requires a value.
    agent_user.email = ""
    agent_user.save(update_fields=["email"])
    agent_contact = Contact.objects.create(
        first_name="Carol",
        last_name="Agent",
        user=agent_user,
    )
    quotation = quotation_line.quotation
    quotation.agent = agent_contact
    quotation.save(update_fields=["agent", "updated_at"])

    hold = _make_expired_hold(
        property_=quotation_line.property,
        quotation=quotation,
        reason=BookingHoldReason.QUOTATION_OPEN.value,
    )

    expire_holds()

    assert _logs_for_hold(hold) == []
