"""Person resolvers for staff-API contact reads.

GAP-045 Unit 3c-2a cut every staff-API read of a customer's name / email /
phone over to the unified ``accounts.Person`` mirror with a transitional
fallback to the legacy ``reservations.Guest`` columns; Unit 3d-3 removed that
fallback so ``person`` is now the sole source (the ``guest`` columns are
dropped in 3d-4). A ``None`` person — or an empty value on it — resolves to
``None``/``""``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounts.models import Person


def contact_name(person: Person | None) -> str | None:
    """The person's display name, or ``None``."""
    if person is not None and person.display_name:
        return person.display_name
    return None


def contact_first_name(person: Person | None) -> str:
    """The person's first name, or ``""``.

    Returns ``""`` rather than ``None`` so it drops straight into a greeting
    merge field (a render context value of ``None`` would print ``"None"``).
    The comms/payments send paths use ``comms.recipients.recipient_first_name``
    instead — same shape, but reachable from the top of the import spine; this
    one is for the reservations-internal quotation render seam, which cannot
    import ``comms`` (upward edge).
    """
    if person is not None and person.first_name:
        return person.first_name
    return ""


def contact_email(person: Person | None) -> str | None:
    """The person's primary email, or ``None``."""
    if person is not None:
        return person.primary_email()
    return None


def contact_phone(person: Person | None) -> str | None:
    """The person's primary phone, or ``None``."""
    if person is not None:
        return person.primary_phone()
    return None
