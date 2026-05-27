"""Build the transactional graph: Enquiry -> Quotation -> Booking, then walk
each booking a step down its state machine for status variety.

Repeat-guest pool is initialised here on first call so later stages
(`extra_quotations`, `orphan_enquiries`, `notes`, …) can reuse it via
`ctx.guest_pool`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, cast

from django.db import transaction
from django.utils import timezone

from core.seed._booking_helpers import (
    advance_status,
    next_stay_start,
    pick_guest,
    populate_payments,
)
from core.seed.context import SeedContext
from core.seed.registry import Stage, register
from reservations.factories import EnquiryFactory, GuestFactory
from reservations.models.enquiry import Enquiry
from reservations.services.bookings import BookingService
from reservations.services.quotations import QuotationService


def _init_guest_pool(ctx: SeedContext) -> None:
    """One-shot init of the repeat-guest pool the first time bookings runs."""
    if ctx.guest_pool:
        return
    for _ in range(ctx.knobs.repeat_guest_pool_size):
        ctx.guest_pool.append(GuestFactory())


def _terms_for(prop: Any, ctx: SeedContext) -> Any:
    """Pick the currently-published TermsVersion. The seeder always wants a
    single canonical row for the booking it's opening, so the v2 multi-row
    setup picks the current one."""
    return ctx.terms[0]


def _currency_for(prop: Any, ctx: SeedContext) -> Any:
    """Return the property's own currency (the RatePlan it was built with)."""
    plan = prop.rate_plans.first()
    if plan is None:
        return ctx.default_currency
    return plan.currency


def _run(ctx: SeedContext) -> int:
    if not ctx.properties:
        return 0
    _init_guest_pool(ctx)
    active_properties = [p for p in ctx.properties if p.status == "active"] or ctx.properties
    expires_at = timezone.now() + timedelta(days=7)
    cursors: dict[int, date] = {}
    made = 0
    for i in range(ctx.n_bookings):
        prop = active_properties[i % len(active_properties)]
        date_from = next_stay_start(prop, cursors, ctx)
        date_to = date_from + timedelta(days=7)
        cursors[prop.pk] = date_to + timedelta(days=7)

        guest = pick_guest(ctx)
        terms = _terms_for(prop, ctx)
        currency = _currency_for(prop, ctx)
        enquiry = cast(
            Enquiry,
            EnquiryFactory(guest=guest, property=prop, date_from=date_from, date_to=date_to),
        )
        ctx.enquiry_pks.append(enquiry.pk)
        with transaction.atomic():
            quotation = QuotationService.create_from_enquiry(
                enquiry,
                [
                    {
                        "property": prop,
                        "date_from": date_from,
                        "date_to": date_to,
                        "adults": 2,
                        "children": 1,
                    }
                ],
                currency=currency,
                terms_version=terms,
                expires_at=expires_at,
            )
            line = quotation.lines.first()
            if line is None:
                raise RuntimeError("QuotationService produced no lines")
            quotation.send()
            requires_pre_approval = bool(
                cast(Any, prop.settings).effective("bookings_require_pre_approval")
            )
            if not requires_pre_approval:
                quotation.accept(line)
            booking = BookingService.create_from_quotation_line(line, terms_version=terms)
            ctx.booking_pks.append(booking.pk)
            populate_payments(booking)
            advance_status(booking, i, ctx)
            from reservations.enums import BookingStatus, EnquiryStatus

            booking.refresh_from_db()
            if booking.status not in (
                BookingStatus.DECLINED.value,
                BookingStatus.PENDING_OWNER_APPROVAL.value,
            ):
                enquiry.refresh_from_db()
                # `Quotation.accept()` now flips the parent enquiry to
                # CONVERTED inside its own atomic block (T3.2), so we only
                # need to convert here if accept() hasn't already done so.
                if enquiry.status != EnquiryStatus.CONVERTED.value:
                    enquiry.convert(quotation)
        made += 1
    return made


register(Stage(name="bookings", run=_run, depends_on=("properties",)))
