"""Shared render-context builders for transactional email.

Both the live send path (``comms.signals``) and the operator-facing template
preview (``/email-templates/{key}/preview``) need to turn a domain object into
the merge-field dict a template renders against. Keeping the builders here —
the single source of truth — means the preview an operator sees is byte-for-byte
what a live send produces; there's no second, drifting implementation.

``comms`` sits at the top of the import spine, so reaching down into
``reservations`` is allowed by the layering contract. Model imports are kept
local to each function to avoid import-time cycles during app loading.
"""

from __future__ import annotations

from typing import Any

from comms.recipients import recipient_first_name
from core.formats import format_date


def booking_context(booking: Any) -> dict[str, Any]:
    # The charge breakdown is built for every booking email so the operator
    # preview matches a live send; only the templates that opt in (the
    # confirmation, today) render it. Import kept local per this module's
    # no-import-time-cycles convention.
    from reservations.services.charges import booking_charge_breakdown

    return {
        "booking_reference": booking.reference,
        "guest_first_name": recipient_first_name(booking.person),
        "property_name": booking.property.display_name or booking.property.name,
        "date_from": format_date(booking.date_from),
        "date_to": format_date(booking.date_to),
        "charge_breakdown": booking_charge_breakdown(booking),
    }


def payment_context(payment: Any) -> dict[str, Any]:
    booking = payment.booking
    return {
        "booking_reference": booking.reference,
        "payment_reference": payment.reference,
        "amount": f"{payment.amount:.2f}",
        "currency": payment.currency.code,
        "guest_first_name": recipient_first_name(booking.person),
        "failure_reason": payment.failure_reason or "",
    }


def resolve_context(
    *,
    context: dict[str, Any] | None = None,
    booking_id: int | None = None,
    quotation_id: int | None = None,
) -> dict[str, Any]:
    """Resolve the render context for a template preview.

    Precedence:

    1. A non-empty explicit ``context`` dict (operator-supplied merge fields)
       wins outright — it's the "render against these exact values" path. An
       empty dict is treated as "no explicit context" so it doesn't silently
       shadow a ``booking_id`` / ``quotation_id`` sent alongside it.
    2. Otherwise dispatch on the provided id to the matching domain builder,
       reusing the same prefetching the live send relies on.
    3. With neither, return ``{}`` — Django renders missing variables as the
       empty string (``string_if_invalid``), which is the acceptable "blank
       skeleton" preview against no data.

    There is deliberately no sample-context catalogue: a curated set of fake
    field values is a drift trap (it rots as templates gain fields) and the
    spec doesn't require it. Preview supplies a real id or an explicit context.
    """
    if context:
        return dict(context)
    if booking_id is not None:
        from django.shortcuts import get_object_or_404

        from reservations.models import Booking

        booking = get_object_or_404(
            Booking.objects.select_related("person", "property", "currency").prefetch_related(
                "charge_items"
            ),
            pk=booking_id,
        )
        return booking_context(booking)
    if quotation_id is not None:
        from django.shortcuts import get_object_or_404

        from reservations.models import Quotation
        from reservations.services.quotation_render import build_quotation_context

        quotation = get_object_or_404(
            Quotation.objects.select_related("person", "agent"),
            pk=quotation_id,
        )
        return build_quotation_context(quotation)
    return {}
