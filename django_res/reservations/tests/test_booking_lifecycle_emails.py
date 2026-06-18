"""Round-trip tests for booking-lifecycle email orchestration.

Each test drives a real state transition through `Booking` or
`BookingService` and asserts the comms signal handler dispatches the
expected `EmailLog` row. The `system_profile` fixture comes from
`django_res/conftest.py`; the locmem email backend in test settings
keeps `send_email_log.delay(...)` from hitting real SMTP.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from accounts.enums import ContactRole
from accounts.models import Person
from accounts.models.person import PersonEmail
from comms.enums import EmailLogStatus
from comms.models import EmailLog
from properties.models import PropertyContactAssignment
from properties.models.settings import PropertySettings
from reservations.enums import BookingStatus
from reservations.models import Booking
from reservations.services.bookings import BookingService

if TYPE_CHECKING:
    from comms.models import SmtpProfile
    from properties.models import Property
    from reservations.models import QuotationLine, TermsVersion

# Lifecycle email dispatch is deferred to transaction.on_commit; run those hooks
# immediately so these round-trip tests observe the dispatched EmailLog.
pytestmark = pytest.mark.usefixtures("run_on_commit_immediately")


def _assign_owner(property_: Property, email: str) -> Person:
    contact = Person.objects.create(first_name="Olive", last_name="Owner")
    PersonEmail.objects.create(contact=contact, email=email, is_primary=True)
    PropertyContactAssignment.objects.create(
        property=property_,
        contact=contact,
        role=ContactRole.OWNER,
        is_primary=True,
    )
    return contact


def _logs_for(template_key: str, booking: Booking) -> list[EmailLog]:
    return list(
        EmailLog.objects.filter(
            template_key=template_key,
            correlation__booking_id=booking.pk,
        )
    )


@pytest.fixture
def lifecycle_templates(db: None) -> None:
    """Re-seed the on-disk templates so the tests don't depend on migrate order."""
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates()


@pytest.mark.django_db
def test_auto_accept_dispatches_booking_confirmation(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    assert booking.status == BookingStatus.AWAITING_DEPOSIT.value
    logs = _logs_for("booking.confirmation", booking)
    assert len(logs) == 1
    assert quotation_line.quotation.guest is not None
    assert logs[0].to == [quotation_line.quotation.guest.email]
    assert logs[0].status == EmailLogStatus.SENT


@pytest.mark.django_db
def test_pre_approval_property_dispatches_owner_approval_request(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    property_ = quotation_line.property
    PropertySettings.objects.create(property=property_, bookings_require_pre_approval=True)
    _assign_owner(property_, "owner@example.com")

    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    assert booking.status == BookingStatus.PENDING_OWNER_APPROVAL.value
    owner_logs = _logs_for("owner.approval_request", booking)
    assert len(owner_logs) == 1
    assert owner_logs[0].to == ["owner@example.com"]
    # The guest does not see a confirmation yet.
    assert _logs_for("booking.confirmation", booking) == []


@pytest.mark.django_db
def test_owner_approve_dispatches_booking_confirmation(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    property_ = quotation_line.property
    PropertySettings.objects.create(property=property_, bookings_require_pre_approval=True)
    _assign_owner(property_, "owner@example.com")
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    booking.owner_approve()

    confirmations = _logs_for("booking.confirmation", booking)
    assert len(confirmations) == 1
    assert quotation_line.quotation.guest is not None
    assert confirmations[0].to == [quotation_line.quotation.guest.email]


@pytest.mark.django_db
def test_owner_decline_dispatches_booking_declined(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    property_ = quotation_line.property
    PropertySettings.objects.create(property=property_, bookings_require_pre_approval=True)
    _assign_owner(property_, "owner@example.com")
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    booking.owner_decline("Owner is unavailable")

    declined = _logs_for("booking.declined", booking)
    assert len(declined) == 1
    assert quotation_line.quotation.guest is not None
    assert declined[0].to == [quotation_line.quotation.guest.email]


@pytest.mark.django_db
def test_cancel_dispatches_booking_cancelled(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    booking.cancel("Guest withdrew")

    cancelled = _logs_for("booking.cancelled", booking)
    assert len(cancelled) == 1
    assert quotation_line.quotation.guest is not None
    assert cancelled[0].to == [quotation_line.quotation.guest.email]


@pytest.mark.django_db
def test_check_out_dispatches_booking_checked_out(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    # Walk forward to CHECKED_IN — the transition path the auto-checkout task uses.
    booking.record_deposit()
    booking.record_balance()
    booking.check_in()

    booking.check_out()

    checked_out = _logs_for("booking.checked_out", booking)
    assert len(checked_out) == 1


@pytest.mark.django_db
def test_invalid_transition_does_not_emit_email(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    from core.exceptions import InvalidTransition

    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    EmailLog.objects.filter(correlation__booking_id=booking.pk).delete()

    with pytest.raises(InvalidTransition):
        # Already AWAITING_DEPOSIT; submit() requires DRAFT.
        booking.submit()

    assert EmailLog.objects.filter(correlation__booking_id=booking.pk).count() == 0


@pytest.mark.django_db
def test_pending_owner_approval_with_no_owner_does_not_crash_transition(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    PropertySettings.objects.create(
        property=quotation_line.property,
        bookings_require_pre_approval=True,
    )

    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    assert booking.status == BookingStatus.PENDING_OWNER_APPROVAL.value
    assert _logs_for("owner.approval_request", booking) == []


@pytest.mark.django_db
def test_replaying_transition_signal_is_idempotent(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """A repeat fire of the same signal payload must not duplicate the EmailLog."""
    from reservations.signals import booking_transitioned

    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    assert len(_logs_for("booking.confirmation", booking)) == 1

    booking_transitioned.send(
        sender=Booking,
        booking=booking,
        from_status=BookingStatus.DRAFT.value,
        to_status=BookingStatus.AWAITING_DEPOSIT.value,
        actor=None,
        source="system",
    )

    assert len(_logs_for("booking.confirmation", booking)) == 1


@pytest.mark.django_db
def test_send_confirmation_email_resends_latest_log(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """The booking-level resend action mints a second confirmation EmailLog."""
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    [original] = _logs_for("booking.confirmation", booking)

    booking.send_confirmation_email()

    logs = _logs_for("booking.confirmation", booking)
    assert len(logs) == 2
    resend = next(log for log in logs if log.pk != original.pk)
    assert resend.correlation.get("resent_from") == original.pk
    assert resend.to == original.to
    assert resend.rendered_subject == original.rendered_subject


@pytest.mark.django_db
def test_send_confirmation_email_falls_back_to_fresh_send(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """When no prior log exists, the resend hook sends a fresh confirmation."""
    PropertySettings.objects.create(
        property=quotation_line.property,
        bookings_require_pre_approval=True,
    )
    _assign_owner(quotation_line.property, "owner@example.com")
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    assert booking.status == BookingStatus.PENDING_OWNER_APPROVAL.value
    assert _logs_for("booking.confirmation", booking) == []

    booking.send_confirmation_email()

    logs = _logs_for("booking.confirmation", booking)
    assert len(logs) == 1
    assert quotation_line.quotation.guest is not None
    assert logs[0].to == [quotation_line.quotation.guest.email]
    assert "resent_from" not in (logs[0].correlation or {})


@pytest.mark.django_db
def test_send_confirmation_email_terminal_booking_raises(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """Cancelled/declined/expired bookings can't be resent."""
    from core.exceptions import InvalidTransition

    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    booking.cancel("Guest withdrew")
    EmailLog.objects.filter(correlation__booking_id=booking.pk).delete()

    with pytest.raises(InvalidTransition):
        booking.send_confirmation_email()

    assert EmailLog.objects.filter(correlation__booking_id=booking.pk).count() == 0


@pytest.mark.django_db
def test_booking_service_writes_single_event_via_transition(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """The refactor must still emit exactly one BookingEvent for the initial step."""
    from reservations.models import BookingEvent

    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    events = list(BookingEvent.objects.filter(booking=booking))
    assert len(events) == 1
    assert events[0].from_status == BookingStatus.DRAFT.value
    assert events[0].to_status == BookingStatus.AWAITING_DEPOSIT.value
    assert events[0].meta == {"quotation_line_id": quotation_line.pk}
