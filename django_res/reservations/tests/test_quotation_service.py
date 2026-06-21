"""Tests for QuotationService.create_from_enquiry."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from django.utils import timezone

from properties.enums import PrefilledChangeOverDay
from properties.models.settings import PropertySettings
from reservations.enums import (
    BookingHoldReason,
    ContactMethod,
    EnquirySource,
    EnquiryStatus,
)
from reservations.models import BookingHold, Enquiry, Quotation
from reservations.services.person_sync import person_for_guest
from reservations.services.quotations import QuotationService

if TYPE_CHECKING:
    from pricing.models import Currency, RateRule
    from properties.models import Property
    from reservations.models import Guest, TermsVersion


@pytest.mark.django_db
def test_create_from_enquiry_happy_path(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,  # ensures PricingEngine has something to quote on
) -> None:
    enquiry = Enquiry.objects.create(
        guest=guest, person=person_for_guest(guest), email=guest.email or ""
    )
    expires = timezone.now() + timedelta(days=7)

    quotation = QuotationService.create_from_enquiry(
        enquiry,
        [
            {
                "property": property_,
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 17),
                "adults": 2,
                "children": 0,
            },
        ],
        terms_version=terms,
        expires_at=expires,
    )

    assert isinstance(quotation, Quotation)
    assert quotation.lines.count() == 1
    line = quotation.lines.first()
    assert line is not None
    assert line.pricing_snapshot["rate_subtotal"] == "1400.00"

    # Quoting is the soft part of the sales process — no hold is placed
    # automatically; holds are a separate, deliberate operator action.
    assert BookingHold.objects.filter(quotation=quotation).count() == 0

    # Enquiry advanced to QUOTED.
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.QUOTED.value


@pytest.mark.django_db
def test_create_from_enquiry_does_not_reprice_manual_line(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> None:
    """A manual enquiry line keeps its supplied total — the engine must not
    clobber it, mirroring the API `_reprice` guard."""
    from decimal import Decimal

    enquiry = Enquiry.objects.create(
        guest=guest, person=person_for_guest(guest), email=guest.email or ""
    )

    quotation = QuotationService.create_from_enquiry(
        enquiry,
        [
            {
                "property": property_,
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 17),
                "adults": 2,
                "children": 0,
                "is_manual": True,
                "currency": gbp,
                "total": Decimal("750.00"),
            },
        ],
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=7),
    )

    line = quotation.lines.get()
    assert line.is_manual is True
    # Engine price would be 7 nights @ £200 = £1400; the manual total survives.
    assert line.total == Decimal("750.00")
    assert line.pricing_snapshot == {}


@pytest.mark.django_db
def test_create_from_enquiry_requires_person(
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> None:
    """An enquiry with no captured customer cannot be quoted (GAP-045 D5-2)."""
    enquiry = Enquiry.objects.create(email="anonymous@example.com")
    assert enquiry.person is None
    with pytest.raises(ValueError):
        QuotationService.create_from_enquiry(
            enquiry,
            [
                {
                    "property": property_,
                    "date_from": date(2026, 6, 10),
                    "date_to": date(2026, 6, 17),
                    "adults": 2,
                },
            ],
            terms_version=terms,
            expires_at=timezone.now() + timedelta(days=7),
        )


@pytest.mark.django_db
@pytest.mark.parametrize("final_status", [EnquiryStatus.LOST.value, EnquiryStatus.CONVERTED.value])
def test_create_from_enquiry_rejects_final_enquiry(
    final_status: str,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> None:
    """A lost/converted enquiry is closed to new quotes — the service rejects
    it with a 400-mapping ValidationError and writes nothing."""
    from rest_framework.exceptions import ValidationError

    enquiry = Enquiry.objects.create(
        guest=guest, person=person_for_guest(guest), email=guest.email or "", status=final_status
    )

    with pytest.raises(ValidationError):
        QuotationService.create_from_enquiry(
            enquiry,
            [
                {
                    "property": property_,
                    "date_from": date(2026, 6, 10),
                    "date_to": date(2026, 6, 17),
                    "adults": 2,
                },
            ],
            terms_version=terms,
            expires_at=timezone.now() + timedelta(days=7),
        )

    assert Quotation.objects.filter(enquiry=enquiry).count() == 0


@pytest.mark.django_db
def test_create_from_enquiry_records_send_path_smtp(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> None:
    """Bug #6: `QuotationService.create_from_enquiry` was calling
    `enquiry.quote_sent(quotation, actor=actor)` with no `meta`, so the
    resulting EnquiryEvent had no `send_path` key — breaking the invariant
    the manual-mark endpoint relies on. The service path is SMTP by
    contract (Quotation built off the back of an enquiry, dispatched
    through the in-app flow), so the event must carry send_path='smtp'.
    """
    from reservations.enums import EnquiryEventKind
    from reservations.models import EnquiryEvent

    enquiry = Enquiry.objects.create(
        guest=guest, person=person_for_guest(guest), email=guest.email or ""
    )

    QuotationService.create_from_enquiry(
        enquiry,
        [
            {
                "property": property_,
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 17),
                "adults": 2,
            },
        ],
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=7),
    )

    event = EnquiryEvent.objects.get(enquiry=enquiry, kind=EnquiryEventKind.QUOTE_SENT.value)
    assert event.meta.get("send_path") == "smtp"


@pytest.mark.django_db
def test_quote_sent_requires_send_path(guest: Guest, gbp: Currency, terms: TermsVersion) -> None:
    """`Enquiry.quote_sent` must require `send_path` — surfacing the audit
    contract in the signature so future callers can't omit it silently."""
    enquiry = Enquiry.objects.create(
        guest=guest, person=person_for_guest(guest), email=guest.email or ""
    )
    quotation = Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        person=person_for_guest(guest),
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )

    with pytest.raises(TypeError):
        enquiry.quote_sent(quotation)  # type: ignore[call-arg]


@pytest.mark.django_db
def test_create_from_enquiry_shifts_off_changeover_arrival(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> None:
    """An off-changeover arrival is never rejected: the engine nudges it
    forward to the property's changeover day and the shifted dates are
    persisted onto the line, with the original arrival surfaced on the
    snapshot for the "we moved your dates" note (GAP-007). A subsequent
    manual hold then protects the shifted dates, not the raw request."""
    PropertySettings.objects.create(
        property=property_,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    enquiry = Enquiry.objects.create(
        guest=guest, person=person_for_guest(guest), email=guest.email or ""
    )
    # 2026-06-10 is a Wednesday — not the Saturday changeover day.
    line_input = {
        "property": property_,
        "date_from": date(2026, 6, 10),
        "date_to": date(2026, 6, 17),
        "adults": 2,
    }

    quotation = QuotationService.create_from_enquiry(
        enquiry,
        [line_input],
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=7),
    )

    assert quotation.lines.count() == 1
    line = quotation.lines.get()
    # Line carries the shifted dates (Wed 06-10 → Sat 06-13, nights preserved).
    assert line.date_from == date(2026, 6, 13)
    assert line.date_to == date(2026, 6, 20)
    assert line.pricing_snapshot["changeover_shifted_from"] == "2026-06-10"

    # No automatic hold — but a manual one holds the shifted dates the
    # line was actually priced on, not the raw request.
    assert BookingHold.objects.filter(quotation=quotation).count() == 0
    hold = QuotationService.hold_line(line)
    assert hold.date_from == date(2026, 6, 13)
    assert hold.date_to == date(2026, 6, 20)


@pytest.mark.django_db
def test_backfill_links_orphaned_holds_to_their_line(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """The 0026 backfill links a pre-FK hold (quotation set, quotation_line NULL)
    to its line by the (quotation, property, dates) key it was placed on."""
    import importlib

    from django.apps import apps as global_apps

    migration = importlib.import_module(
        "reservations.migrations.0026_backfill_bookinghold_quotation_line"
    )

    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        person=person_for_guest(guest),
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = quotation.lines.create(
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
    )
    # A hold as the pre-FK code left it: quotation set, quotation_line NULL.
    hold = BookingHold.objects.create(
        property=property_,
        quotation=quotation,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=quotation.expires_at,
        reason=BookingHoldReason.QUOTATION_OPEN.value,
    )
    assert hold.quotation_line_id is None

    migration._link_holds_to_lines(global_apps, None)

    hold.refresh_from_db()
    assert hold.quotation_line_id == line.pk


def _quotation_with_line(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    *,
    date_from: date = date(2026, 6, 10),
    date_to: date = date(2026, 6, 17),
) -> tuple[Quotation, Any]:
    """Bare ORM quotation + line — no service side effects, no holds."""
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        person=person_for_guest(guest),
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = quotation.lines.create(
        property=property_,
        currency=gbp,
        date_from=date_from,
        date_to=date_to,
        adults=2,
    )
    return quotation, line


@pytest.mark.django_db
def test_hold_line_places_hold_with_property_default_expiry(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """A manual line hold is QUOTATION_OPEN, carries the line FKs, and expires
    per the property's effective `hold_duration_hours` — NOT the quotation's
    `expires_at` (holds are now a deliberate operator action, decoupled from
    quote paperwork)."""
    PropertySettings.objects.create(property=property_, hold_duration_hours=24)
    quotation, line = _quotation_with_line(guest, gbp, terms, property_)

    before = timezone.now()
    hold = QuotationService.hold_line(line)
    after = timezone.now()

    assert hold.reason == BookingHoldReason.QUOTATION_OPEN.value
    assert hold.quotation_id == quotation.pk
    assert hold.quotation_line_id == line.pk
    assert hold.date_from == line.date_from
    assert hold.date_to == line.date_to
    assert hold.released_at is None
    assert hold.expires_at is not None
    assert hold.expires_at != quotation.expires_at
    assert before + timedelta(hours=24) <= hold.expires_at <= after + timedelta(hours=24)


@pytest.mark.django_db
def test_hold_line_falls_back_to_group_default_expiry(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """No PropertySettings row → the 48-hour group default applies."""
    _, line = _quotation_with_line(guest, gbp, terms, property_)

    before = timezone.now()
    hold = QuotationService.hold_line(line)
    after = timezone.now()

    assert hold.expires_at is not None
    assert before + timedelta(hours=48) <= hold.expires_at <= after + timedelta(hours=48)


@pytest.mark.django_db
def test_hold_line_is_idempotent(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """A second hold_line on an already-held line returns the live hold."""
    _, line = _quotation_with_line(guest, gbp, terms, property_)

    first = QuotationService.hold_line(line)
    second = QuotationService.hold_line(line)

    assert second.pk == first.pk
    assert BookingHold.objects.count() == 1


@pytest.mark.django_db
def test_hold_line_raises_when_dates_already_held(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    from core.exceptions import HoldUnavailable
    from reservations.services.holds import HoldService

    _, line = _quotation_with_line(guest, gbp, terms, property_)
    HoldService.place(
        property=property_,
        date_from=date(2026, 6, 12),
        date_to=date(2026, 6, 15),
    )

    with pytest.raises(HoldUnavailable):
        QuotationService.hold_line(line)
    assert not BookingHold.objects.filter(quotation_line=line).exists()


@pytest.mark.django_db
def test_release_line_hold_releases_and_is_idempotent(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    _, line = _quotation_with_line(guest, gbp, terms, property_)
    hold = QuotationService.hold_line(line)

    assert QuotationService.release_line_hold(line) == 1
    hold.refresh_from_db()
    assert hold.released_at is not None

    # Releasing an un-held line is a no-op, not an error.
    assert QuotationService.release_line_hold(line) == 0


@pytest.mark.django_db
def test_move_line_hold_moves_dates_preserving_expiry(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """Editing a held line's dates relocates the hold; the operator-set expiry
    window is preserved (the hold does not re-anchor to the quotation)."""
    _, line = _quotation_with_line(guest, gbp, terms, property_)
    hold = QuotationService.hold_line(line)
    original_expiry = hold.expires_at

    line.date_from = date(2026, 6, 20)
    line.date_to = date(2026, 6, 27)
    line.save(update_fields=["date_from", "date_to"])

    moved = QuotationService.move_line_hold(line)

    assert moved is not None
    assert moved.pk == hold.pk
    assert moved.date_from == date(2026, 6, 20)
    assert moved.date_to == date(2026, 6, 27)
    assert moved.expires_at == original_expiry


@pytest.mark.django_db
def test_move_line_hold_without_live_hold_is_noop(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """An un-held line stays un-held through edits — moving never places."""
    _, line = _quotation_with_line(guest, gbp, terms, property_)

    assert QuotationService.move_line_hold(line) is None
    assert BookingHold.objects.count() == 0


@pytest.mark.django_db
def test_move_line_hold_conflict_raises_and_leaves_hold_in_place(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    from core.exceptions import HoldUnavailable
    from reservations.services.holds import HoldService

    _, line = _quotation_with_line(guest, gbp, terms, property_)
    hold = QuotationService.hold_line(line)
    HoldService.place(
        property=property_,
        date_from=date(2026, 6, 20),
        date_to=date(2026, 6, 27),
    )

    line.date_from = date(2026, 6, 21)
    line.date_to = date(2026, 6, 26)
    line.save(update_fields=["date_from", "date_to"])

    with pytest.raises(HoldUnavailable):
        QuotationService.move_line_hold(line)

    hold.refresh_from_db()
    assert hold.date_from == date(2026, 6, 10)
    assert hold.date_to == date(2026, 6, 17)


@pytest.mark.django_db
def test_create_direct_auto_creates_agent_portal_enquiry(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> None:
    """Agent-direct quote with no enquiry mints exactly one AGENT_PORTAL enquiry."""
    guest.contact_method = ContactMethod.EMAIL
    guest.save(update_fields=["contact_method"])
    person = person_for_guest(guest)

    quotation = QuotationService.create_direct(
        person=person,
        lines=[
            {
                "property": property_,
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 17),
                "adults": 2,
                "children": 0,
            },
        ],
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=7),
    )

    # Exactly one enquiry, linked, tagged AGENT_PORTAL, carrying the snapshot.
    assert Enquiry.objects.count() == 1
    enquiry = quotation.enquiry
    assert enquiry is not None
    assert enquiry.site_source == EnquirySource.AGENT_PORTAL.value
    # GAP-045 3d-C: `person` is the sole persisted customer FK; the guest
    # snapshot still seeds the denormalised contact fields below.
    assert enquiry.guest_id is None
    assert enquiry.person_id == person_for_guest(guest).pk
    assert enquiry.email == guest.email
    assert enquiry.contact_method == ContactMethod.EMAIL.value
    # The service path advances the enquiry to QUOTED (audited).
    assert enquiry.status == EnquiryStatus.QUOTED.value
    # And conversion reporting sees it.
    assert quotation.lines.count() == 1


@pytest.mark.django_db
def test_create_from_enquiry_seeds_line_inclusions_from_plan(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> None:
    """Service-path lines are seeded from the winning plan's inclusion text
    too — parity with the API `add_line` path (legacy ResService.cs:1241)."""
    plan = rate_rule.card.plan
    plan.inclusion = "Daily maid service"
    plan.save(update_fields=["inclusion"])
    enquiry = Enquiry.objects.create(
        guest=guest, person=person_for_guest(guest), email=guest.email or ""
    )

    quotation = QuotationService.create_from_enquiry(
        enquiry,
        [
            {
                "property": property_,
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 17),
                "adults": 2,
                "children": 0,
            },
        ],
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=7),
    )

    line = quotation.lines.get()
    assert line.inclusions == "Daily maid service"
