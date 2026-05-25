"""Recipient resolution helpers for lifecycle email handlers.

Kept out of `comms.signals` so each helper is unit-testable without
firing signals. The handlers compose these and pass the result to
`EmailService.send`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from accounts.enums import ContactRole

if TYPE_CHECKING:
    from accounts.models import Contact, User
    from properties.models import Property
    from reservations.models import Guest, Quotation


def guest_email(guest: Guest | None) -> str | None:
    """Return the guest's email address, or `None` if unset/anonymised."""
    if guest is None:
        return None
    email = getattr(guest, "email", "") or ""
    return email or None


def _primary_contact_email(contact: Contact | None) -> str | None:
    if contact is None:
        return None
    primary = contact.emails.filter(is_primary=True).first()
    if primary is not None:
        return primary.email
    any_email = contact.emails.first()
    return any_email.email if any_email is not None else None


def primary_owner_email(property_: Property) -> str | None:
    """Email of the primary active OWNER contact on the property.

    `None` when no owner is currently assigned or none has an email on
    file. Callers must treat `None` as "skip the email, don't crash".
    """
    assignment = (
        property_.contact_assignments.filter(
            role=ContactRole.OWNER,
            is_primary=True,
            end_date__isnull=True,
        )
        .select_related("contact")
        .first()
    )
    if assignment is None:
        return None
    return _primary_contact_email(assignment.contact)


def agent_user_for(quotation: Quotation) -> User | None:
    """The `User` behind a quotation's agent Contact, or `None`.

    Used to drive `EmailService` toward the agent's personal SMTP
    profile. Returns `None` when the quotation has no agent or the
    agent contact has no linked user account.
    """
    agent = getattr(quotation, "agent", None)
    if agent is None:
        return None
    return getattr(agent, "user", None)
