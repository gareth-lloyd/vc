"""Shared render seam for a Quotation.

`build_quotation_context` assembles the render context **once**, and
`render_quotation_html` turns it into a self-contained, inline-CSS HTML
document. Both are the single source of truth consumed by the quotation
email, the (later) preview modal, and copy-to-clipboard — so the quote a
guest sees in their inbox is byte-for-byte what an operator previews.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.template.loader import render_to_string

from core.text import render_markdown

if TYPE_CHECKING:
    from reservations.models.quotation import Quotation, QuotationLine


# Sensible English defaults. These become operator-overridable in a later
# phase; centralised here so the email and the preview share one wording.
DEFAULT_INTRO = "Thank you for your enquiry. Please find your personalised quotation below."
DEFAULT_SIGNOFF = "We look forward to welcoming you. Reply to this email with any questions."


def _money(amount: Decimal) -> str:
    """Format a Decimal as a thousands-grouped 2-dp string, e.g. `1,234.00`."""
    return f"{amount:,.2f}"


def _hero_image_url(line: QuotationLine) -> str | None:
    """Best-effort absolute-or-relative URL for the line property's hero image.

    Thin wrapper over `Property.hero_image_url()` — the single source of
    truth shared with the line serializer and the bulk-quote API.
    """
    return line.property.hero_image_url()


def build_quotation_context(
    quotation: Quotation,
    *,
    subject: str | None = None,
    intro: str | None = None,
    signoff: str | None = None,
) -> dict[str, Any]:
    """Assemble the render context for a quotation, once.

    Prefetches `lines → property → images` so the per-line `hero_image()`
    walk doesn't N+1. The returned dict is the contract the email template,
    the preview modal, and copy-to-clipboard all consume — extend it
    additively.

    `subject` / `intro` / `signoff` are operator copy overrides: when None
    the centralised defaults apply, so the preview and the dispatched email
    never drift. A non-None override replaces the default in the returned
    context (and thus in the rendered HTML and the email subject).
    """
    lines_qs = (
        quotation.lines.exclude(legacy_id__startswith="booking-")
        .select_related("property")
        .prefetch_related("property__images")
    )

    line_dicts: list[dict[str, Any]] = []
    grand_total = Decimal("0")
    for line in lines_qs:
        grand_total += line.total
        nights = (line.date_to - line.date_from).days
        line_dicts.append(
            {
                "property_name": line.property.display_name or line.property.name,
                "date_from": line.date_from,
                "date_to": line.date_to,
                "nights": nights,
                "adults": line.adults,
                "children": line.children,
                "total": _money(line.total),
                "discount": _money(line.discount),
                "inclusions": line.inclusions,
                "hero_image_url": _hero_image_url(line),
                "notes": line.notes,
            }
        )

    guest = quotation.guest
    agent = quotation.agent
    agent_name = ""
    if agent is not None:
        agent_name = f"{agent.first_name} {agent.last_name}".strip()

    terms_version = quotation.terms_version
    terms_html = render_markdown(terms_version.body_markdown) if terms_version else ""

    return {
        "lines": line_dicts,
        "guest_first_name": guest.first_name,
        "guest_full_name": f"{guest.first_name} {guest.last_name}".strip(),
        "agent_name": agent_name,
        "quotation_reference": quotation.reference,
        "currency_code": quotation.currency.code,
        "grand_total": _money(grand_total),
        "expires_at": quotation.expires_at,
        "terms_html": terms_html,
        "subject": subject if subject is not None else f"Your quotation {quotation.reference}",
        "intro": intro if intro is not None else DEFAULT_INTRO,
        "signoff": signoff if signoff is not None else DEFAULT_SIGNOFF,
    }


def render_quotation_html(quotation: Quotation) -> str:
    """Render the branded, self-contained quote HTML for a quotation."""
    return render_to_string(
        "reservations/quotation_quote.html",
        build_quotation_context(quotation),
    )
