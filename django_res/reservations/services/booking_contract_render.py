"""Shared render seam for a booking's contract document (GAP-094).

`build_contract_context` assembles the render context **once**;
`render_contract_html` turns it into a self-contained, inline-CSS, print-
oriented HTML document; `render_contract_pdf` prints that HTML to PDF bytes.
The staff preview endpoint and the stored `BookingDocument` PDF both consume
this seam, so what an operator previews is what the guest receives.

Mirrors `reservations.services.quotation_render`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from django.template.loader import render_to_string
from django.utils import timezone

from core.exceptions import UnsupportedDocumentKind
from core.formats import format_date
from core.logging.operations import log_operation
from core.pdf import html_to_pdf
from core.text import render_markdown
from reservations.serializers._contact_reads import contact_name
from reservations.services.charges import _money, booking_charge_breakdown

# One vocabulary for "which payment rows are the guest's schedule", shared with
# the owner-money walk rather than re-copied here. Both are string literals in
# `owner_finance` because `reservations` sits below `payments` in the
# import-linter layers; `payments/tests/test_component_splits_parity.py` pins
# them against the real enums.
from reservations.services.owner_finance import _SCHEDULE_PURPOSES, _TERMINAL_NON_ACTIVE

if TYPE_CHECKING:
    from reservations.models.booking import Booking

logger = structlog.get_logger(__name__)

# Document kinds this seam can render. The allowlist lives here, not in the
# view, so the generate service (Unit 5) and the preview endpoint refuse the
# same set.
_RENDERABLE_KINDS = frozenset({"contract"})

_PURPOSE_LABELS = {"deposit": "Deposit", "balance": "Balance"}

# On top of the rows `owner_finance` already treats as non-active, a contract
# schedule also drops `waived` (never chargeable) and `refunded` (money already
# returned) — neither is something the guest is being asked to pay.
_NOT_PAYABLE = _TERMINAL_NON_ACTIVE | {"waived", "refunded"}
_SETTLED = "succeeded"


def _payment_schedule(booking: Booking) -> list[dict[str, Any]]:
    """Deposit/balance rows on the guest's schedule, oldest first per purpose.

    Walks `booking.payments.all()` in Python (prefetch-friendly, mirrors
    `owner_finance.payment_component_splits`) and drops rows the guest owes
    nothing on, so a superseded/cancelled deposit never appears. A settled row
    stays on the schedule but carries `is_paid` — a contract that listed a
    paid deposit as outstanding would be read as a demand for it twice.
    """
    rows = sorted(booking.payments.all(), key=lambda p: (p.created_at, p.pk))
    schedule: list[dict[str, Any]] = []
    for purpose in _SCHEDULE_PURPOSES:
        for payment in rows:
            if payment.purpose != purpose or payment.status in _NOT_PAYABLE:
                continue
            schedule.append(
                {
                    "label": _PURPOSE_LABELS[purpose],
                    "amount": _money(payment.amount),
                    "due_at": format_date(payment.due_at) if payment.due_at else None,
                    "is_paid": payment.status == _SETTLED,
                }
            )
    return schedule


def build_contract_context(booking: Booking) -> dict[str, Any]:
    """Assemble the contract render context for a booking, once.

    House rules come from `booking.house_rules_snapshot` (stamped at
    confirmation), never the property's live rules. They go into the context
    as **plain text**, not HTML: the field is free-text a villa owner typed,
    so running it through `render_markdown` would restructure a `#`, `1.`,
    `*` or an indented line into markup the author never asked for (and
    `render_markdown` passes raw HTML straight through). The template applies
    `|linebreaks` under autoescape instead — newlines wrap, markup is inert.
    """
    prop = booking.property
    terms_version = booking.terms_version
    snapshot = booking.house_rules_snapshot.strip()
    return {
        "booking_reference": booking.reference,
        "property_name": prop.display_name or prop.name,
        "region_name": prop.region.name,
        "country_name": prop.region.country.name,
        "date_from": format_date(booking.date_from),
        "date_to": format_date(booking.date_to),
        "nights": (booking.date_to - booking.date_from).days,
        "guest_full_name": contact_name(booking.person) or "",
        "adults": booking.adults,
        "children": booking.children,
        "breakdown": booking_charge_breakdown(booking),
        "payment_schedule": _payment_schedule(booking),
        # Operator-authored Markdown, unlike the house rules above.
        "terms_html": render_markdown(terms_version.body_markdown) if terms_version else "",
        # `Booking.terms_accepted_at` is non-null — every booking is created
        # through the conversion service, which stamps it.
        "terms_accepted_at": format_date(booking.terms_accepted_at),
        "house_rules": snapshot,
        # A body with no timestamp was reconstructed by the 0010 backfill;
        # the template says so instead of claiming it was agreed.
        "house_rules_recorded_at": (
            format_date(booking.house_rules_snapshot_at)
            if booking.house_rules_snapshot_at
            else None
        ),
        "house_rules_reconstructed": booking.house_rules_reconstructed,
        "generated_on": format_date(timezone.localdate()),
    }


def render_contract_html(booking: Booking) -> str:
    """Render the self-contained contract HTML for a booking."""
    return render_to_string("reservations/booking_contract.html", build_contract_context(booking))


def render_document_html(booking: Booking, kind: str) -> str:
    """Render a booking document of `kind`, or raise `UnsupportedDocumentKind`.

    The single entry point for "give me this document's HTML": callers hand
    over an untrusted `kind` string and get either HTML or a 400-shaped domain
    error, so the preview endpoint and the generate service can't drift on
    which kinds exist.
    """
    if kind not in _RENDERABLE_KINDS:
        raise UnsupportedDocumentKind(f"Unsupported document kind {kind!r}.")
    return render_contract_html(booking)


def render_contract_pdf(booking: Booking, *, html: str | None = None) -> bytes:
    """Render the contract to PDF bytes (WeasyPrint via `core.pdf`).

    Pass `html` when the caller already rendered it (the generate service
    stores the HTML alongside the PDF) so the template runs once, not twice.
    Raises `OSError` if the native toolchain is missing — see `core.pdf`.
    """
    with log_operation("booking.contract_pdf", logger=logger, booking_id=booking.pk) as ctx:
        pdf = html_to_pdf(render_contract_html(booking) if html is None else html)
        ctx["size_bytes"] = len(pdf)
        return pdf
