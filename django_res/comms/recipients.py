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
    """Primary email of a Person, or `None`.

    Thin delegate to `Person.primary_email()` — the canonical is-primary-then-
    oldest resolver (`comms → accounts` is a legal downward edge). Reads the
    `prefetch_related("emails")` cache when one exists, and fails closed for an
    ANONYMIZED Person (the model guard), so an anonymised sentinel address is
    never surfaced to a send.
    """
    if contact is None:
        return None
    return contact.primary_email()


def recipient_email(person: Person | None, guest: Guest | None) -> str | None:
    """Customer recipient address, person-first with the guest as fallback.

    GAP-045 Unit 3c-2b: transactional sends resolve the recipient from the
    unified `accounts.Person` mirror, falling back to the legacy `Guest.email`
    while `person` is still null (fallback removed in 3d). Person-first means an
    anonymised Person fails closed (`primary_email()` returns None) instead of
    leaking through the guest column.
    """
    return _primary_contact_email(person) or guest_email(guest)


def recipient_first_name(person: Person | None, guest: Guest | None) -> str:
    """Greeting first name, person-first with the guest as fallback.

    Value-gated, not existence-gated: a Person with a blank `first_name` still
    falls through to the guest's. Returns `""` (templates render the empty
    greeting) rather than `None` so callers can drop it straight into a context.
    """
    if person is not None and person.first_name:
        return person.first_name
    if guest is not None:
        return guest.first_name or ""
    return ""


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
