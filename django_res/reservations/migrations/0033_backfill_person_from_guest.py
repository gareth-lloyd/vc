"""GAP-045 Unit 3b — backfill ``accounts.Person`` from ``reservations.Guest``
and populate the parallel ``person`` FKs added in Unit 3a (0032).

Creates exactly one Person per Guest (no auto-dedup — resolved with the user),
copies the PII / address / status / preference fields, and materialises the
Guest's single email/phone as ``PersonEmail`` / ``PersonPhone`` children. Then
links every row that carries a ``guest`` FK to the matching Person via its
parallel ``person`` FK.

Idempotency: keyed on ``Person.legacy_id = "guest-{guest.pk}"`` — a namespaced
sentinel used ONLY as this migration's upsert key, never an application lookup
(honours the CLAUDE.md "legacy_id is migration metadata only" rule). Re-running
is a no-op: existing Persons are matched, FK passes filter on ``person__isnull``.

Audit: RunPython operates on *historical* models (``apps.get_model``), so the
``pre_save`` / ``post_delete`` audit signals — connected to the concrete model
classes in ``AppConfig.ready`` — do not fire. The FK link pass additionally uses
``bulk_update`` / ``update``, which bypass those signals even on the concrete
tracked models (Enquiry/Quotation/Booking/BookingGuest). Both bypasses are
intentional: a one-time system backfill needs no per-row audit trail — the same
posture ``Guest.merge`` / ``Contact.merge`` take with their ``.update()`` FK
rewrites. ``person_id`` joins each model's ``track()`` list in Unit 3c when real
read/write paths start mutating it.

Still no behaviour change: nothing reads or writes ``person`` yet (Unit 3c).
"""

from __future__ import annotations

from django.db import migrations

# Guest status (reservations.enums.GuestStatus) → Person status
# (accounts.enums.PersonStatus). Literals, not enum imports, so a future enum
# edit can't retroactively change this historical migration.
_STATUS_MAP = {
    "active": "active",
    "archived": "inactive",
    "anonymized": "anonymized",
}

# Models carrying a parallel ``person`` FK alongside ``guest`` (Unit 3a).
_FK_MODELS = ("Enquiry", "Quotation", "Booking", "BookingGuest", "GuestPreference")


def _forwards(apps, schema_editor):
    Guest = apps.get_model("reservations", "Guest")
    Person = apps.get_model("accounts", "Person")
    PersonEmail = apps.get_model("accounts", "PersonEmail")
    PersonPhone = apps.get_model("accounts", "PersonPhone")

    guest_to_person: dict[int, int] = {}

    for guest in Guest.objects.all().iterator():
        # Literal "guest-" is frozen here (migrations must not import mutable app
        # code); mirrored by accounts.models.GUEST_LEGACY_PREFIX, which the
        # /contacts viewset uses to filter these rows out until Unit 3c.
        person, created = Person.objects.update_or_create(
            legacy_id=f"guest-{guest.pk}",
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
                # Person.preferred_method is NOT NULL (default EMAIL); Guest's is
                # nullable. Flat EMAIL when unset — matches ContactLoader, which
                # defaults every Contact-derived Person to EMAIL (resolved with
                # the user).
                "preferred_method": guest.contact_method or "email",
                "anonymized_at": guest.anonymized_at,
                # user OneToOne deferred to Unit 3d: a User already linked to a
                # Contact-derived Person can't also take a Guest-derived one.
            },
        )
        guest_to_person[guest.pk] = person.pk

        # Children only on first creation — re-runs already have them, and the
        # one-primary-per-contact constraint would reject duplicates anyway.
        if created:
            # Guest.save collapses empty email to NULL, so truthiness is the
            # honest "has an email" test.
            if guest.email:
                PersonEmail.objects.create(
                    contact=person,
                    email=guest.email,
                    label="primary",
                    is_primary=True,
                )
            # Copy whatever Guest stored verbatim — Guest.save already ran
            # to_e164 (unparseable numbers pass through trimmed-raw), and
            # PersonPhone enforces no format.
            if guest.phone:
                PersonPhone.objects.create(
                    contact=person,
                    number=guest.phone,
                    label="mobile",
                    is_primary=True,
                )

    _link_person_fks(apps, guest_to_person)


def _link_person_fks(apps, guest_to_person):
    """Set ``person_id`` from each row's ``guest_id``, idempotently.

    ``Booking.person`` resolves through ``Booking.guest`` — the denormalised
    LEAD ``BookingGuest.guest`` — so it lands on the same Person as the LEAD
    row by construction; one shared mapping keeps them single-sourced.
    """
    for model_name in _FK_MODELS:
        model = apps.get_model("reservations", model_name)
        rows = list(
            model.objects.filter(person__isnull=True, guest__isnull=False).only("pk", "guest_id")
        )
        for row in rows:
            # Every Guest was processed in the forward pass above (same
            # transaction), so a direct lookup is total — fail loud on a missing
            # key rather than silently writing person_id=NULL.
            row.person_id = guest_to_person[row.guest_id]
        if rows:
            model.objects.bulk_update(rows, ["person_id"], batch_size=1000)


def _reverse(apps, schema_editor):
    """Unlink the parallel FKs, then delete the Guest-derived Persons.

    Deleting the ``guest-`` Persons must drop their PersonEmail/PersonPhone
    children too. Safe because nothing else points at them yet (reads cut over
    in Unit 3c) and the parallel reservations FKs are nulled just above.

    We do NOT use ``QuerySet.delete()`` on Person: its cascade collector issues a
    ``SELECT *``, and the *historical* Person here carries columns added by
    LATER accounts migrations (e.g. ``agency_id`` from 0011) — the migration
    state accumulates the whole topological plan, not just this node's
    ancestors. During a project-wide *backwards* run those later migrations have
    already dropped their columns before this reverse executes, so a ``SELECT *``
    references a column that no longer exists. We therefore touch only ``id``
    (via ``values_list``) and a raw DELETE, never the ahead-of-DB columns.
    """
    for model_name in _FK_MODELS:
        model = apps.get_model("reservations", model_name)
        model.objects.filter(person__legacy_id__startswith="guest-").update(person=None)

    Person = apps.get_model("accounts", "Person")
    PersonEmail = apps.get_model("accounts", "PersonEmail")
    PersonPhone = apps.get_model("accounts", "PersonPhone")

    guest_person_pks = list(
        Person.objects.filter(legacy_id__startswith="guest-").values_list("pk", flat=True)
    )
    PersonEmail.objects.filter(contact_id__in=guest_person_pks).delete()
    PersonPhone.objects.filter(contact_id__in=guest_person_pks).delete()
    persons = Person.objects.filter(pk__in=guest_person_pks)
    persons._raw_delete(persons.db)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_person_country_person_marketing_consent_and_more"),
        ("reservations", "0032_booking_person_bookingguest_person_enquiry_person_and_more"),
    ]

    operations = [
        migrations.RunPython(_forwards, _reverse),
    ]
