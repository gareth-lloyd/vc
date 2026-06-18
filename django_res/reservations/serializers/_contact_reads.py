"""Person-first / guest-fallback resolvers for staff-API contact reads.

GAP-045 Unit 3c-2a cuts every staff-API read of a customer's name / email /
phone over to the unified ``accounts.Person`` mirror, falling back to the
legacy ``reservations.Guest`` columns while ``person`` is still null (the
fallback is removed in 3d, once every row is linked and ``guest`` is dropped).

The chain is **value-gated**, not existence-gated: an empty-name (or
email-less) Person still falls through to the guest's value rather than
short-circuiting on ``person is not None``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounts.models import Person
    from reservations.models import Guest


def contact_name(person: Person | None, guest: Guest | None) -> str | None:
    """Person display name, else the guest's name, else ``None``."""
    if person is not None and person.display_name:
        return person.display_name
    if guest is not None:
        return f"{guest.first_name} {guest.last_name}".strip() or None
    return None


def contact_first_name(person: Person | None, guest: Guest | None) -> str:
    """Person first name, else the guest's, else ``""`` (value-gated).

    Returns ``""`` rather than ``None`` so it drops straight into a greeting
    merge field (a render context value of ``None`` would print ``"None"``).
    The comms/payments send paths use ``comms.recipients.recipient_first_name``
    instead — same shape, but reachable from the top of the import spine; this
    one is for the reservations-internal quotation render seam, which cannot
    import ``comms`` (upward edge).
    """
    if person is not None and person.first_name:
        return person.first_name
    if guest is not None:
        return guest.first_name or ""
    return ""


def contact_email(person: Person | None, guest: Guest | None) -> str | None:
    """Person primary email, else the guest's email, else ``None``."""
    if person is not None:
        email = person.primary_email()
        if email:
            return email
    if guest is not None:
        return guest.email or None
    return None


def contact_phone(person: Person | None, guest: Guest | None) -> str | None:
    """Person primary phone, else the guest's phone, else ``None``."""
    if person is not None:
        phone = person.primary_phone()
        if phone:
            return phone
    if guest is not None:
        return guest.phone or None
    return None
