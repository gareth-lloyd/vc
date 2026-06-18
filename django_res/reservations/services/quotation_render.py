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

from django.conf import settings
from django.template.loader import render_to_string

from core.formats import format_date
from core.text import render_markdown
from reservations.serializers._contact_reads import contact_first_name, contact_name

if TYPE_CHECKING:
    from reservations.models.quotation import Quotation, QuotationLine


# Sensible English defaults. These become operator-overridable in a later
# phase; centralised here so the email and the preview share one wording.
DEFAULT_INTRO = "Thank you for your enquiry. Please find your personalised quotation below."
DEFAULT_SIGNOFF = "We look forward to welcoming you. Reply to this email with any questions."


def _money(amount: Decimal) -> str:
    """Format a Decimal as a thousands-grouped 2-dp string, e.g. `1,234.00`."""
    return f"{amount:,.2f}"


def _absolute_media_url(url: str | None) -> str | None:
    """Make a media URL absolute for the email / preview / clipboard render.

    `Property.hero_image_url()` returns `image.url`, which under the
    dev/WhiteNoise config (`FileSystemStorage`, `MEDIA_URL="/media/"`) is a
    host-relative path with no scheme/domain. The render seam embeds it as an
    `<img src>` in copy-to-Outlook HTML and a sandboxed (null-origin) preview
    iframe, where a relative src can't resolve — so the guest gets a broken
    thumbnail.

    `FRONTEND_URL` is the canonical public origin: production/staging is a
    single-origin deploy where Django (WhiteNoise) serves both the SPA and
    `/media/`, so it is the host that actually serves the file. Only prefix a
    host-relative path (starts with `/`); a storage that already returns an
    absolute URL (e.g. S3, `http(s)://…`) is left untouched so we never
    double-prefix.
    """
    if url is None or not url.startswith("/"):
        return url
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}{url}"


def _hero_image_url(line: QuotationLine) -> str | None:
    """Absolute URL for the line property's hero image, or None.

    Thin wrapper over `Property.hero_image_url()` — the single source of
    truth shared with the line serializer and the bulk-quote API — absolutised
    for the email / preview / clipboard render so the `<img src>` resolves off
    the same-origin SPA. (The API serializer keeps the relative form; the SPA
    consumes it same-origin.)
    """
    return _absolute_media_url(line.property.hero_image_url())


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

    `subject` is special-cased: a blank/whitespace override (the FE sends `""`
    when the operator clears the field) coerces to the default — a blank email
    subject is never acceptable. `intro`/`signoff` keep `is not None`
    semantics: `""` is a legitimate "no paragraph" and is respected.
    """
    lines_qs = (
        quotation.lines.real()
        .select_related("property", "currency")
        .prefetch_related("property__images")
    )

    line_dicts: list[dict[str, Any]] = []
    for line in lines_qs:
        nights = (line.date_to - line.date_from).days
        line_dicts.append(
            {
                "property_name": line.property.display_name or line.property.name,
                "date_from": format_date(line.date_from),
                "date_to": format_date(line.date_to),
                "nights": nights,
                "adults": line.adults,
                "children": line.children,
                # Per-line currency (GAP-014): legacy quote emails freely
                # mixed £/€/$ across options, so each line renders its own.
                "currency_code": line.currency.code,
                "total": _money(line.total),
                "discount": _money(line.discount),
                "inclusions": line.inclusions,
                "hero_image_url": _hero_image_url(line),
                "notes": line.notes,
            }
        )

    agent = quotation.agent
    agent_name = ""
    if agent is not None:
        agent_name = f"{agent.first_name} {agent.last_name}".strip()

    terms_version = quotation.terms_version
    terms_html = render_markdown(terms_version.body_markdown) if terms_version else ""

    return {
        "lines": line_dicts,
        # GAP-045 Unit 3c-2b: resolve the customer name person-first (guest
        # fallback while `person` is null). quotation_render is in reservations
        # and cannot import comms, so it uses the same-app `_contact_reads`
        # resolvers rather than `comms.recipients.recipient_first_name`.
        "guest_first_name": contact_first_name(quotation.person, quotation.guest),
        "guest_full_name": contact_name(quotation.person, quotation.guest) or "",
        "agent_name": agent_name,
        "quotation_reference": quotation.reference,
        # Customer-facing "valid until" — the stored UTC time would render
        # misleadingly, so the date alone is shown; expiry stays server-enforced.
        "expires_at": format_date(quotation.expires_at) if quotation.expires_at else None,
        "terms_html": terms_html,
        "subject": (subject or "").strip() or f"Your quotation {quotation.reference}",
        "intro": intro if intro is not None else DEFAULT_INTRO,
        "signoff": signoff if signoff is not None else DEFAULT_SIGNOFF,
    }


def render_quotation_html(
    quotation: Quotation,
    *,
    subject: str | None = None,
    intro: str | None = None,
    signoff: str | None = None,
) -> str:
    """Render the branded, self-contained quote HTML for a quotation.

    `subject`/`intro`/`signoff` are the same operator copy overrides accepted
    by `build_quotation_context`; they're threaded through so the preview HTML
    reflects the operator's in-flight edits. The no-arg call renders defaults.
    """
    return render_to_string(
        "reservations/quotation_quote.html",
        build_quotation_context(quotation, subject=subject, intro=intro, signoff=signoff),
    )
