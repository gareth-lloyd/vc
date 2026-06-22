"""Person primary-channel reconcilers.

In-place reconcilers that keep a `Person`'s single PRIMARY email / phone in sync
with one authoritative source column, without ever blind-creating a SECOND
PRIMARY row (which would trip `one_primary_email_per_contact` /
`one_primary_phone_per_contact` on a re-run).

Used by the legacy `ClientLoader` (VillaClientDetails → Person) and — until
`Guest` is retired (GAP-045 D5-4) — the Guest→Person mirror. Lives in `accounts`
(spine bottom) so both the loader and reservations can import it.
"""

from __future__ import annotations

from accounts.enums import EmailLabel, PhoneLabel
from accounts.models import Person, PersonEmail, PersonPhone


def reconcile_primary_email(person: Person, email: str | None) -> None:
    """Make the Person's PRIMARY email match a single source email column.

    Assumes this is the only writer of the row's PRIMARY channel: it manages
    exactly the one PRIMARY row. If a secondary channel equal to the new value
    is ever added by another path, the in-place update could trip
    `unique_contact_email` — revisit when channels gain another writer.
    """
    existing = person.emails.filter(is_primary=True).first()
    if email:
        if existing is None:
            PersonEmail.objects.create(
                contact=person,
                email=email,
                label=EmailLabel.PRIMARY.value,
                is_primary=True,
            )
        elif existing.email != email:
            existing.email = email
            existing.save(update_fields=["email", "updated_at"])
    elif existing is not None:
        # A falsy source email means "no email" (Guest.save collapses "" → NULL)
        # — drop the PRIMARY row so comms can't pick up a dead address.
        existing.delete()


def reconcile_primary_phone(person: Person, phone: str) -> None:
    """Make the Person's PRIMARY phone match a single source phone column.

    Shared in-place reconciler — see `reconcile_primary_email` for the why.
    """
    existing = person.phones.filter(is_primary=True).first()
    if phone:
        if existing is None:
            PersonPhone.objects.create(
                contact=person,
                number=phone,
                label=PhoneLabel.MOBILE.value,
                is_primary=True,
            )
        elif existing.number != phone:
            existing.number = phone
            existing.save(update_fields=["number", "updated_at"])
    elif existing is not None:
        existing.delete()
