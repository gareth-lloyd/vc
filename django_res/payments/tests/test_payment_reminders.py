"""Tests for `payments.tasks.send_payment_reminders`.

The task is the Django redesign of the legacy `PaymentReminderSchedulerJob`
documented in `workflows/12-automation/scheduler-jobs.md`. It walks PENDING
deposit / balance / security-deposit rows and dispatches the appropriate
`comms` template when "today" crosses the trigger threshold.

Idempotency is provided by ``EmailService.send`` keying on
``(template_key, version, sorted(to), correlation)`` — a second run on the
same day must not double-send.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from django.utils import timezone

from comms.models import EmailLog
from payments.enums import (
    PaymentPurpose,
    PaymentStatus,
    SecurityDepositKind,
    SecurityDepositStatus,
)
from payments.models import Payment, SecurityDeposit
from payments.tasks import send_payment_reminders
from reservations.enums import BookingStatus

if TYPE_CHECKING:
    from comms.models import SmtpProfile
    from pricing.models import Currency
    from reservations.models import Booking


@pytest.fixture
def lifecycle_templates(db: None) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates()


def _at_noon(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12, 0, tzinfo=UTC)


def _make_payment(
    booking: Booking,
    gbp: Currency,
    *,
    purpose: str,
    due_on: date,
    status: str = PaymentStatus.PENDING.value,
    amount: str = "420.00",
) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=purpose,
        amount=Decimal(amount),
        currency=gbp,
        status=status,
        due_at=_at_noon(due_on),
    )


# ---------------------------------------------------------------------------
# Deposit reminders
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_deposit_due_today_sends_reminder(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    today = date.today()
    payment = _make_payment(booking, gbp, purpose=PaymentPurpose.DEPOSIT.value, due_on=today)

    send_payment_reminders(now=_at_noon(today))

    logs = list(
        EmailLog.objects.filter(
            template_key="payment.reminder.deposit",
            correlation__payment_id=payment.pk,
        )
    )
    assert len(logs) == 1
    assert booking.guest is not None
    assert logs[0].to == [booking.guest.email]


@pytest.mark.django_db
def test_deposit_not_due_today_sends_nothing(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    today = date.today()
    _make_payment(
        booking,
        gbp,
        purpose=PaymentPurpose.DEPOSIT.value,
        due_on=today + timedelta(days=5),
    )

    send_payment_reminders(now=_at_noon(today))

    assert not EmailLog.objects.filter(template_key="payment.reminder.deposit").exists()


# ---------------------------------------------------------------------------
# Balance reminders — T-7 / T-3 / T-0
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("days_before_due", "template_key"),
    [
        (7, "booking.balance_reminder_7d"),
        (3, "booking.balance_reminder_3d"),
        (0, "booking.balance_due_today"),
    ],
)
def test_balance_reminder_fires_on_each_threshold(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
    days_before_due: int,
    template_key: str,
) -> None:
    today = date.today()
    due_on = today + timedelta(days=days_before_due)
    payment = _make_payment(
        booking,
        gbp,
        purpose=PaymentPurpose.BALANCE.value,
        due_on=due_on,
        amount="980.00",
    )

    send_payment_reminders(now=_at_noon(today))

    logs = list(
        EmailLog.objects.filter(
            template_key=template_key,
            correlation__payment_id=payment.pk,
        )
    )
    assert len(logs) == 1
    assert booking.guest is not None
    assert logs[0].to == [booking.guest.email]


@pytest.mark.django_db
def test_balance_far_from_due_sends_nothing(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """Delta well above the highest threshold (7) → no reminder yet."""
    today = date.today()
    _make_payment(
        booking,
        gbp,
        purpose=PaymentPurpose.BALANCE.value,
        due_on=today + timedelta(days=30),
        amount="980.00",
    )

    send_payment_reminders(now=_at_noon(today))

    assert not EmailLog.objects.filter(
        template_key__startswith="booking.balance_",
    ).exists()


# ---------------------------------------------------------------------------
# Catch-up — a missed cron day must not silently drop reminders
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_balance_reminder_catches_up_after_missed_cron_day(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """Cron missed T-7; the next run (T-5) still fires the 7d reminder."""
    today = date.today()
    payment = _make_payment(
        booking,
        gbp,
        purpose=PaymentPurpose.BALANCE.value,
        due_on=today + timedelta(days=5),
        amount="980.00",
    )

    send_payment_reminders(now=_at_noon(today))

    assert (
        EmailLog.objects.filter(
            template_key="booking.balance_reminder_7d",
            correlation__payment_id=payment.pk,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_balance_reminder_fires_each_threshold_in_sequence(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """Across runs at T-7, T-3, T-0 the 7d / 3d / 0d templates fire once each."""
    today = date.today()
    payment = _make_payment(
        booking,
        gbp,
        purpose=PaymentPurpose.BALANCE.value,
        due_on=today + timedelta(days=7),
        amount="980.00",
    )

    send_payment_reminders(now=_at_noon(today))
    send_payment_reminders(now=_at_noon(today + timedelta(days=4)))
    send_payment_reminders(now=_at_noon(today + timedelta(days=7)))

    keys = list(
        EmailLog.objects.filter(correlation__payment_id=payment.pk)
        .order_by("queued_at")
        .values_list("template_key", flat=True)
    )
    assert keys == [
        "booking.balance_reminder_7d",
        "booking.balance_reminder_3d",
        "booking.balance_due_today",
    ]


@pytest.mark.django_db
def test_overdue_balance_still_sends_due_today_once(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """Past the due date with 0d already sent → no further send (no spam)."""
    today = date.today()
    payment = _make_payment(
        booking,
        gbp,
        purpose=PaymentPurpose.BALANCE.value,
        due_on=today,
        amount="980.00",
    )

    send_payment_reminders(now=_at_noon(today))
    send_payment_reminders(now=_at_noon(today + timedelta(days=2)))

    assert (
        EmailLog.objects.filter(
            template_key="booking.balance_due_today",
            correlation__payment_id=payment.pk,
        ).count()
        == 1
    )


# ---------------------------------------------------------------------------
# Status & arrival guards
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_already_paid_payment_is_skipped(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    today = date.today()
    _make_payment(
        booking,
        gbp,
        purpose=PaymentPurpose.DEPOSIT.value,
        due_on=today,
        status=PaymentStatus.SUCCEEDED.value,
    )

    send_payment_reminders(now=_at_noon(today))

    assert not EmailLog.objects.filter(template_key="payment.reminder.deposit").exists()


@pytest.mark.django_db
def test_past_arrival_booking_is_skipped(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """Legacy filter: `where ArrivalDate.Date >= UtcNow.Date`."""
    booking.date_from = date.today() - timedelta(days=1)
    booking.date_to = date.today() - timedelta(days=1) + timedelta(days=2)
    booking.save(update_fields=["date_from", "date_to", "updated_at"])

    today = date.today()
    _make_payment(booking, gbp, purpose=PaymentPurpose.DEPOSIT.value, due_on=today)

    send_payment_reminders(now=_at_noon(today))

    assert not EmailLog.objects.filter(template_key="payment.reminder.deposit").exists()


# ---------------------------------------------------------------------------
# Idempotency — re-running on the same day must not double-send
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rerunning_the_task_does_not_double_send(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    today = date.today()
    payment = _make_payment(booking, gbp, purpose=PaymentPurpose.DEPOSIT.value, due_on=today)

    send_payment_reminders(now=_at_noon(today))
    send_payment_reminders(now=_at_noon(today))

    assert (
        EmailLog.objects.filter(
            template_key="payment.reminder.deposit",
            correlation__payment_id=payment.pk,
        ).count()
        == 1
    )


# ---------------------------------------------------------------------------
# Security-deposit reminders
# ---------------------------------------------------------------------------


def _make_sd(
    booking: Booking,
    gbp: Currency,
    *,
    due_on: date,
    kind: SecurityDepositKind = SecurityDepositKind.BT_REFUNDABLE,
    status: str = SecurityDepositStatus.AWAITING_BT.value,
) -> SecurityDeposit:
    return SecurityDeposit.objects.create(
        booking=booking,
        kind=kind.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=status,
        due_at=_at_noon(due_on),
    )


@pytest.mark.django_db
@pytest.mark.parametrize("days_before_due", [7, 0])
def test_security_deposit_reminder_fires_at_t_minus_7_and_due_date(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
    days_before_due: int,
) -> None:
    today = date.today()
    sd = _make_sd(booking, gbp, due_on=today + timedelta(days=days_before_due))

    send_payment_reminders(now=_at_noon(today))

    logs = list(
        EmailLog.objects.filter(
            template_key="payment.security_deposit_request",
            correlation__security_deposit_id=sd.pk,
        )
    )
    assert len(logs) == 1


@pytest.mark.django_db
def test_security_deposit_in_terminal_state_is_skipped(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    today = date.today()
    _make_sd(
        booking,
        gbp,
        due_on=today,
        status=SecurityDepositStatus.HELD.value,
    )

    send_payment_reminders(now=_at_noon(today))

    assert not EmailLog.objects.filter(
        template_key="payment.security_deposit_request",
    ).exists()


@pytest.mark.django_db
def test_security_deposit_catches_up_after_missed_t7_cron(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """Cron missed T-7; next run at T-5 still sends the early heads-up."""
    today = date.today()
    sd = _make_sd(booking, gbp, due_on=today + timedelta(days=5))

    send_payment_reminders(now=_at_noon(today))

    assert (
        EmailLog.objects.filter(
            template_key="payment.security_deposit_request",
            correlation__security_deposit_id=sd.pk,
            correlation__reminder_band=7,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_security_deposit_t7_and_arrival_both_fire_independently(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """T-7 (anchored on due_at) and arrival (anchored on date_from) fire as
    distinct logical reminders; one does not suppress the other."""
    today = date.today()
    # `booking` fixture sets date_from = today + 60. Drive the T-7 from due_at
    # and the arrival nudge from date_from on the same SecurityDeposit.
    sd = _make_sd(booking, gbp, due_on=today + timedelta(days=7))

    send_payment_reminders(now=_at_noon(today))
    send_payment_reminders(now=_at_noon(booking.date_from))

    bands = sorted(
        EmailLog.objects.filter(
            template_key="payment.security_deposit_request",
            correlation__security_deposit_id=sd.pk,
        ).values_list("correlation__reminder_band", flat=True)
    )
    assert bands == [0, 7]


# ---------------------------------------------------------------------------
# SD anchor — T-0 must key off arrival (booking.date_from), not due_at
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sd_arrival_band_fires_on_date_from_not_due_at(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """SD whose due_at lands 14 days before arrival: at today == due_at the
    *early* band fires, not the arrival band. At today == arrival the
    arrival band fires."""
    arrival = booking.date_from
    due_on = arrival - timedelta(days=14)
    sd = _make_sd(booking, gbp, due_on=due_on)

    # On the SD due date: early band only.
    send_payment_reminders(now=_at_noon(due_on))
    early_only = list(
        EmailLog.objects.filter(
            correlation__security_deposit_id=sd.pk,
        ).values_list("correlation__reminder_band", flat=True)
    )
    assert early_only == [7]

    # On the arrival date: arrival band fires too.
    send_payment_reminders(now=_at_noon(arrival))
    both = sorted(
        EmailLog.objects.filter(
            correlation__security_deposit_id=sd.pk,
        ).values_list("correlation__reminder_band", flat=True)
    )
    assert both == [0, 7]


@pytest.mark.django_db
def test_sd_early_band_anchors_on_due_at_even_when_arrival_is_distant(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """due_at 7 days out, arrival 30 days out → only the early band fires."""
    today = date.today()
    booking.date_from = today + timedelta(days=30)
    booking.date_to = booking.date_from + timedelta(days=7)
    booking.save(update_fields=["date_from", "date_to", "updated_at"])
    sd = _make_sd(booking, gbp, due_on=today + timedelta(days=7))

    send_payment_reminders(now=_at_noon(today))

    bands = list(
        EmailLog.objects.filter(
            correlation__security_deposit_id=sd.pk,
        ).values_list("correlation__reminder_band", flat=True)
    )
    assert bands == [7]


@pytest.mark.django_db
def test_sd_arrival_band_fires_when_arrival_today_even_if_due_at_past(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """The previous queryset filter (`booking__date_from__gte=today`) silently
    dropped this case. Confirm the SD-side filter no longer guards it."""
    today = date.today()
    booking.date_from = today
    booking.date_to = today + timedelta(days=7)
    booking.save(update_fields=["date_from", "date_to", "updated_at"])
    # due_at landed 14 days ago — early already missed; arrival is today.
    sd = _make_sd(booking, gbp, due_on=today - timedelta(days=14))

    send_payment_reminders(now=_at_noon(today))

    bands = sorted(
        EmailLog.objects.filter(
            correlation__security_deposit_id=sd.pk,
        ).values_list("correlation__reminder_band", flat=True)
    )
    # Both bands are "uncrossed" and overdue, so both fire on this catch-up
    # tick — the early (delta_to_due == -14) and the arrival (delta_to_arrival
    # == 0). The single-template / two-bands shape is preserved.
    assert bands == [0, 7]


# ---------------------------------------------------------------------------
# CC card-update branch — balance-due-today swaps template when payment_method=CARD
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_balance_due_today_with_card_fires_card_update_template(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    from reservations.enums import PaymentMethod as ReservationsPaymentMethod

    assert booking.payment_method == ReservationsPaymentMethod.CARD.value
    today = date.today()
    payment = _make_payment(
        booking,
        gbp,
        purpose=PaymentPurpose.BALANCE.value,
        due_on=today,
        amount="980.00",
    )
    payment.payment_method = "card"
    payment.save(update_fields=["payment_method", "updated_at"])

    send_payment_reminders(now=_at_noon(today))

    assert (
        EmailLog.objects.filter(
            template_key="payment.card_update_request",
            correlation__payment_id=payment.pk,
            correlation__reminder_band=0,
        ).count()
        == 1
    )
    assert not EmailLog.objects.filter(
        template_key="booking.balance_due_today",
        correlation__payment_id=payment.pk,
    ).exists()


@pytest.mark.django_db
def test_balance_due_today_with_bank_transfer_still_fires_balance_template(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    today = date.today()
    payment = _make_payment(
        booking,
        gbp,
        purpose=PaymentPurpose.BALANCE.value,
        due_on=today,
        amount="980.00",
    )
    payment.payment_method = "bank_transfer"
    payment.save(update_fields=["payment_method", "updated_at"])

    send_payment_reminders(now=_at_noon(today))

    assert (
        EmailLog.objects.filter(
            template_key="booking.balance_due_today",
            correlation__payment_id=payment.pk,
        ).count()
        == 1
    )
    assert not EmailLog.objects.filter(
        template_key="payment.card_update_request",
        correlation__payment_id=payment.pk,
    ).exists()


@pytest.mark.django_db
def test_balance_t7_with_card_still_fires_generic_warning(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """The CC branch is T-0 only; the T-7 heads-up stays generic."""
    today = date.today()
    payment = _make_payment(
        booking,
        gbp,
        purpose=PaymentPurpose.BALANCE.value,
        due_on=today + timedelta(days=7),
        amount="980.00",
    )
    payment.payment_method = "card"
    payment.save(update_fields=["payment_method", "updated_at"])

    send_payment_reminders(now=_at_noon(today))

    assert (
        EmailLog.objects.filter(
            template_key="booking.balance_reminder_7d",
            correlation__payment_id=payment.pk,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_card_update_dedupe_is_band_scoped(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """If the CC branch fires at T-0, a later same-band send must not fire even
    if the operator flips payment_method to bank_transfer between runs."""
    today = date.today()
    payment = _make_payment(
        booking,
        gbp,
        purpose=PaymentPurpose.BALANCE.value,
        due_on=today,
        amount="980.00",
    )
    payment.payment_method = "card"
    payment.save(update_fields=["payment_method", "updated_at"])

    send_payment_reminders(now=_at_noon(today))

    payment.payment_method = "bank_transfer"
    payment.save(update_fields=["payment_method", "updated_at"])
    send_payment_reminders(now=_at_noon(today))

    rows = list(
        EmailLog.objects.filter(
            correlation__payment_id=payment.pk,
            correlation__reminder_band=0,
        ).values_list("template_key", flat=True)
    )
    assert rows == ["payment.card_update_request"]


# ---------------------------------------------------------------------------
# Booking status filter — terminal bookings must not get reminders
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "terminal_status",
    ["cancelled", "expired", "declined", "checked_out"],
)
def test_terminal_booking_does_not_get_reminder(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
    terminal_status: str,
) -> None:
    booking.status = terminal_status
    fields = ["status", "updated_at"]
    if terminal_status == BookingStatus.CANCELLED.value:
        booking.cancelled_at = timezone.now()  # constraint: CANCELLED ⇒ cancelled_at
        fields.append("cancelled_at")
    booking.save(update_fields=fields)
    today = date.today()
    _make_payment(booking, gbp, purpose=PaymentPurpose.DEPOSIT.value, due_on=today)
    _make_sd(booking, gbp, due_on=today)

    send_payment_reminders(now=_at_noon(today))

    assert not EmailLog.objects.exclude(template_key="").exists()


# ---------------------------------------------------------------------------
# Per-row resilience — a single bad row does not abort the whole batch
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_one_failing_row_does_not_abort_the_batch(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row that raises an unexpected error must not block later rows."""
    today = date.today()
    bad_payment = _make_payment(booking, gbp, purpose=PaymentPurpose.DEPOSIT.value, due_on=today)
    good_payment = _make_payment(
        booking,
        gbp,
        purpose=PaymentPurpose.BALANCE.value,
        due_on=today,
        amount="980.00",
    )

    from payments import tasks as tasks_module

    original_dispatch = tasks_module._dispatch

    def explode_for_bad_payment(template_key: str, **kwargs: Any) -> bool:
        if kwargs.get("payment") is not None and kwargs["payment"].pk == bad_payment.pk:
            raise RuntimeError("simulated render failure")
        return original_dispatch(template_key, **kwargs)

    monkeypatch.setattr(tasks_module, "_dispatch", explode_for_bad_payment)

    send_payment_reminders(now=_at_noon(today))

    assert (
        EmailLog.objects.filter(
            template_key="booking.balance_due_today",
            correlation__payment_id=good_payment.pk,
        ).count()
        == 1
    )
    assert not EmailLog.objects.filter(
        correlation__payment_id=bad_payment.pk,
    ).exists()


# ---------------------------------------------------------------------------
# GAP-045 Unit 3c-2b — reminders resolve the recipient person-first
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reminder_sends_to_person_email_when_person_linked(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """A booking linked to a Person whose email differs from the guest's sends
    to the *person* address — proving the reminder resolves person-first, not
    just that the (synced) mirror happens to agree."""
    from reservations.models import Booking as BookingModel
    from reservations.services.person_sync import person_for_guest

    assert booking.guest is not None
    person = person_for_guest(booking.guest)
    person.first_name = "Grace"
    person.save(update_fields=["first_name", "updated_at"])
    primary = person.emails.filter(is_primary=True).first()
    assert primary is not None
    primary.email = "grace@navy.mil"
    primary.save(update_fields=["email", "updated_at"])
    BookingModel.objects.filter(pk=booking.pk).update(person=person)

    today = date.today()
    payment = _make_payment(booking, gbp, purpose=PaymentPurpose.DEPOSIT.value, due_on=today)

    send_payment_reminders(now=_at_noon(today))

    log = EmailLog.objects.get(
        template_key="payment.reminder.deposit",
        correlation__payment_id=payment.pk,
    )
    assert log.to == ["grace@navy.mil"]


@pytest.mark.django_db
def test_reminder_idempotent_when_person_email_equals_guest(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    """The idempotency hash keys on ``to``. In the common synced case the
    person mirror email equals the guest email, so dedupe must still hold
    across the person-first cutover — a re-run sends nothing new."""
    from reservations.models import Booking as BookingModel
    from reservations.services.person_sync import person_for_guest

    assert booking.guest is not None
    person = person_for_guest(booking.guest)
    assert person.primary_email() == booking.guest.email  # synced 1:1
    BookingModel.objects.filter(pk=booking.pk).update(person=person)

    today = date.today()
    payment = _make_payment(booking, gbp, purpose=PaymentPurpose.DEPOSIT.value, due_on=today)

    send_payment_reminders(now=_at_noon(today))
    send_payment_reminders(now=_at_noon(today))

    assert (
        EmailLog.objects.filter(
            template_key="payment.reminder.deposit",
            correlation__payment_id=payment.pk,
        ).count()
        == 1
    )


def test_reminder_context_formats_dates_for_customers() -> None:
    """Stay dates and due_on are long-form ("8 July 2025"), never ISO."""
    from types import SimpleNamespace

    from payments.tasks import _reminder_context

    booking = SimpleNamespace(
        reference="VC-1",
        person=None,  # person-first greeting falls back to the guest
        guest=SimpleNamespace(first_name="Ada"),
        property=SimpleNamespace(display_name="Villa Sol", name="villa-sol"),
        date_from=date(2025, 7, 8),
        date_to=date(2025, 7, 14),
    )

    ctx = _reminder_context(
        booking=booking,  # type: ignore[arg-type]
        amount=Decimal("100.00"),
        currency_code="GBP",
        due_at=datetime(2025, 7, 1, 12, 0, tzinfo=UTC),
        payment=None,
    )

    assert ctx["date_from"] == "8 July 2025"
    assert ctx["date_to"] == "14 July 2025"
    assert ctx["due_on"] == "1 July 2025"
