"""Small shared helpers for the legacy loaders."""

from __future__ import annotations

from typing import Any


def ensure_enquiry(guest: Any, *, legacy_id: str, agent: Any | None = None) -> Any:
    """Idempotently back-create a minimal Enquiry for a Guest.

    Mirrors `QuotationService.minimal_enquiry_for` but keyed on `legacy_id` so
    re-running the import doesn't spawn duplicate enquiries. Used where a legacy
    quotation has no resolvable `EnquireId` (now that `Quotation.enquiry` is
    mandatory). Tagged `AGENT_PORTAL` for conversion-reporting segmentation.
    """
    from reservations.enums import EnquirySource
    from reservations.models.enquiry import Enquiry
    from reservations.services.person_sync import person_for_guest

    enquiry, _ = Enquiry.objects.update_or_create(
        legacy_id=legacy_id,
        defaults={
            "guest": guest,
            # GAP-045 Unit 3c-1b: keep the parallel Person FK in lockstep. Both
            # legacy quotation paths (QuotationLoader, BookingLoader) back-create
            # enquiries through here, so mirroring `person` once covers both.
            "person": person_for_guest(guest),
            "first_name": guest.first_name,
            "last_name": guest.last_name,
            "email": guest.email or "",
            "phone": guest.phone,
            "contact_method": guest.contact_method,
            "agent": agent,
            "site_source": EnquirySource.AGENT_PORTAL.value,
        },
    )
    return enquiry


def legacy_quotation_no(row: dict[str, Any]) -> int | None:
    """Parse the legacy `QuotationNo`, returning a positive int or `None`.

    `0`, NULL, negative, and non-numeric values all map to `None`, so the
    quotation and booking loaders interpret a missing/sentinel `QuotationNo`
    identically (avoiding the `QVC0` / `VC0` references a bare `int()` would
    have produced).
    """
    raw = row.get("QuotationNo")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None
