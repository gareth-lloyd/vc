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

from accounts.enums import PersonKind, PersonPreferredMethod, PersonStatus
from accounts.models import GUEST_LEGACY_PREFIX, Person
from accounts.services.person_channels import reconcile_primary_email, reconcile_primary_phone
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
            # GAP-045 D2: a Guest mirror is always a CUSTOMER (the /contacts
            # directory filters on this; defaults CONTACT for owner/agent rows).
            "kind": PersonKind.CUSTOMER.value,
        },
    )
    reconcile_primary_email(person, guest.email)
    reconcile_primary_phone(person, guest.phone)
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


__all__ = [
    "SYNCED_GUEST_FIELDS",
    "person_for_guest",
    "sync_person_from_guest",
]
