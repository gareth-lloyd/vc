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
    from reservations.models import Quotation


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


def recipient_email(person: Person | None) -> str | None:
    """Customer recipient address from the unified `accounts.Person`.

    GAP-045 Unit 3c-2b cut transactional sends over to the Person mirror; Unit
    3d-3 removed the legacy `Guest.email` fallback, so `person` is the sole
    source. An anonymised Person fails closed (`primary_email()` returns None)
    rather than leaking a sentinel address.
    """
    return _primary_contact_email(person)


def recipient_first_name(person: Person | None) -> str:
    """Greeting first name from the unified `accounts.Person`, or `""`.

    Returns `""` (templates render the empty greeting) rather than `None` so
    callers can drop it straight into a context.
    """
    if person is not None and person.first_name:
        return person.first_name
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
            contact__isnull=False,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gt=today))
        .select_related("contact")
        .prefetch_related("contact__emails")
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
