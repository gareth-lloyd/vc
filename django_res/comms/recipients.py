"""Recipient resolution helpers for lifecycle email handlers.

Kept out of `comms.signals` so each helper is unit-testable without
firing signals. The handlers compose these and pass the result to
`EmailService.send`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

from accounts.enums import ContactRole

if TYPE_CHECKING:
    from accounts.models import Person, User
    from properties.models import Property
    from reservations.models import Guest, Quotation


def guest_email(guest: Guest | None) -> str | None:
    """Return the guest's email address, or `None` if unset/anonymised."""
    if guest is None:
        return None
    email = getattr(guest, "email", "") or ""
    return email or None


def _primary_contact_email(contact: Person | None) -> str | None:
    if contact is None:
        return None
    primary = contact.emails.filter(is_primary=True).first()
    if primary is not None:
        return primary.email
    # Deterministic fallback when no row is flagged primary: oldest email by
    # insertion. PersonEmail has no Meta.ordering, so `.first()` without an
    # explicit `order_by` is heap-order — unstable across VACUUMs.
    any_email = contact.emails.order_by("pk").first()
    return any_email.email if any_email is not None else None


def primary_owner_email(property_: Property) -> str | None:
    """Email of the primary active OWNER contact on the property.

    "Active" means the assignment is either open-ended (`end_date IS NULL`)
    or scheduled to end in the future. An assignment with a past or
    same-day `end_date` is treated as closed.

    `None` when no owner is currently assigned or none has an email on
    file. Callers must treat `None` as "skip the email, don't crash".
    """
    today = timezone.localdate()
    assignment = (
        property_.contact_assignments.filter(
            role=ContactRole.OWNER,
            is_primary=True,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gt=today))
        .select_related("contact")
        .first()
    )
    if assignment is None:
        return None
    return _primary_contact_email(assignment.contact)


def agent_user_for(quotation: Quotation) -> User | None:
    """The `User` behind a quotation's agent Person, or `None`.

    Used to drive `EmailService` toward the agent's personal SMTP
    profile. Returns `None` when the quotation has no agent or the
    agent contact has no linked user account.
    """
    agent = getattr(quotation, "agent", None)
    if agent is None:
        return None
    return getattr(agent, "user", None)
