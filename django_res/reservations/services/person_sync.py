"""Guest → Person mirror (GAP-045 Unit 3c).

Keeps a unified `accounts.Person` in lockstep with each `reservations.Guest`
during the expand/contract cutover. The 3b migration created one Person per
existing Guest (keyed `legacy_id="guest-{pk}"`); this service keeps that Person
up to date for every *new* or *edited* Guest going forward, wired to a `Guest`
`post_save` signal (`reservations.signals`).

The mapping mirrors the 3b backfill migration (reservations/0033) — the migration
keeps its own *frozen* copy because migrations must not import mutable app code;
this is the live version. Once `Guest` is retired in Unit 3d, both this service
and the signal go away.

The Guest↔Person link is `Person.legacy_id == "guest-{guest.pk}"`. This is the
ONE place `legacy_id` is used as a runtime lookup rather than pure migration
metadata (django_res/CLAUDE.md). It is a deliberate, *transitional* exception:
3a added a parallel `person` FK to the five reservation models but no link from
`Guest` itself, so `legacy_id` is the only available correlator during the
cutover. It disappears in 3d when `Guest` is retired. The prefix is the shared
`accounts.models.GUEST_LEGACY_PREFIX` so it stays in lockstep with the
`/contacts` exclusion that hides these mirrors.

The sync runs *inside* the Guest's save transaction (not `on_commit`) on purpose:
a mirror that can't be written should roll back the Guest write too, so a Guest
never exists without its Person.

`person_for_guest` is the read side used by the FK-population layer (Unit 3c-1b):
it returns the Person mirror for a Guest, syncing one into existence first if a
caller somehow runs ahead of the signal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from accounts.enums import EmailLabel, PersonPreferredMethod, PersonStatus, PhoneLabel
from accounts.models import GUEST_LEGACY_PREFIX, Person, PersonEmail, PersonPhone
from reservations.enums import GuestStatus

if TYPE_CHECKING:
    from reservations.models import Guest

# Guest status → Person status. Kept in sync with the frozen copy in
# reservations/migrations/0033.
_STATUS_MAP = {
    GuestStatus.ACTIVE.value: PersonStatus.ACTIVE.value,
    GuestStatus.ARCHIVED.value: PersonStatus.INACTIVE.value,
    GuestStatus.ANONYMIZED.value: PersonStatus.ANONYMIZED.value,
}

# Guest fields synced onto the Person. A Guest save touching none of these (nor
# email/phone) can skip the sync entirely.
SYNCED_GUEST_FIELDS = frozenset(
    {
        "title",
        "first_name",
        "last_name",
        "address_line_1",
        "address_line_2",
        "town",
        "post_code",
        "country",
        "country_id",
        "marketing_consent",
        "notes",
        "status",
        "contact_method",
        "anonymized_at",
        "email",
        "phone",
    }
)


def _legacy_id_for(guest: Guest) -> str:
    return f"{GUEST_LEGACY_PREFIX}{guest.pk}"


def sync_person_from_guest(guest: Guest) -> Person:
    """Create or update the Person mirror for `guest` (idempotent).

    Copies PII / address / status / preference, and reconciles the single
    email/phone into a PRIMARY `PersonEmail` / `PersonPhone` *in place* — a Guest
    edits its one email/phone, so blindly creating children would leave stale
    rows and trip the one-primary-per-contact constraints. The `user` OneToOne is
    deferred to Unit 3d.
    """
    person, _ = Person.objects.update_or_create(
        legacy_id=_legacy_id_for(guest),
        defaults={
            "title": guest.title,
            "first_name": guest.first_name,
            "last_name": guest.last_name,
            "address_line_1": guest.address_line_1,
            "address_line_2": guest.address_line_2,
            "town": guest.town,
            "post_code": guest.post_code,
            "country_id": guest.country_id,
            "marketing_consent": guest.marketing_consent,
            "notes": guest.notes,
            "status": _STATUS_MAP[guest.status],
            "preferred_method": guest.contact_method or PersonPreferredMethod.EMAIL.value,
            "anonymized_at": guest.anonymized_at,
        },
    )
    _reconcile_email(person, guest.email)
    _reconcile_phone(person, guest.phone)
    if guest.status == GuestStatus.ANONYMIZED.value:
        # The Guest has been anonymized (Guest.anonymize scrubbed ITS audit
        # trail). The per-save mirror has been writing the guest's real PII onto
        # the audit-tracked Person all along, so copying the now-redacted values
        # is not enough — scrub the Person's trail too, or erasure leaves the PII
        # recoverable from accounts AuditLog. Person.anonymize() redacts + runs
        # scrub_pii (BUG-012 ordering: scrub after the write).
        person.anonymize()
    return person


def person_for_guest(guest: Guest) -> Person:
    """Return the Person mirror for `guest`, creating it if the signal hasn't run.

    The FK-population layer (Unit 3c-1b) calls this to resolve `<row>.person` from
    `<row>.guest`.
    """
    person = Person.objects.filter(legacy_id=_legacy_id_for(guest)).first()
    if person is not None:
        return person
    return sync_person_from_guest(guest)


def _reconcile_email(person: Person, email: str | None) -> None:
    """Make the Person's PRIMARY email match the Guest's single email column.

    Assumes this sync is the only writer of the mirror's channels (true during
    3c): it manages exactly the one PRIMARY row. If a secondary channel equal to
    the new value is ever added by another path, the in-place update could trip
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
        # Guest.save collapses "" → NULL, so a falsy email means "no email" —
        # drop the mirror so comms can't pick up a dead address.
        existing.delete()


def _reconcile_phone(person: Person, phone: str) -> None:
    """Make the Person's PRIMARY phone match the Guest's single phone column."""
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


__all__ = ["SYNCED_GUEST_FIELDS", "person_for_guest", "sync_person_from_guest"]
