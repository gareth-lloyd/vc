# GAP-045 D5-4c — the destructive finale: re-key the guest-mirror Persons onto
# the `client-{Id}` namespace, then drop the `guest` FK from the five reservation
# models and delete the `Guest` model itself.
#
# The re-key RunPython MUST run BEFORE the RemoveField/DeleteModel ops: it reads
# `reservations.Guest` to resolve each mirror's legacy `VillaClientDetails.Id`,
# so the table has to still exist. Frozen literals only (no app-code imports) —
# migrations must not import mutable app code.

from django.db import migrations

# Mirror Persons are keyed `legacy_id="guest-{guest.pk}"` (the Guest's Django pk);
# the unified customer namespace is `client-{VillaClientDetails.Id}` (the Guest's
# own `legacy_id`). Both literals are frozen here — they mirror
# `accounts.models` (former GUEST_LEGACY_PREFIX, now retired) and
# `data_migration.loaders.sentinels.CLIENT_LEGACY_PREFIX`.
_GUEST_PREFIX = "guest-"
_CLIENT_PREFIX = "client-"


def _rekey_forward(apps, schema_editor):
    """Re-key every `guest-{pk}` mirror Person onto `client-{Id}` (or NULL).

    For each mirror Person:
    - parse the `guest-` suffix (skip malformed, mirroring 0034's `.isdigit()`
      guard);
    - resolve the Guest by that pk; its own `legacy_id` is the legacy
      `VillaClientDetails.Id`;
    - new legacy_id = `client-{Id}` when the Guest (and its legacy_id) exist,
      else NULL (never the literal "client-None");
    - FAIL CLOSED if the target `client-{Id}` already exists on another Person
      (an out-of-order ClientLoader run) — minting a duplicate would silently
      fork the customer. In the canonical migrate-then-loadlegacy order no
      `client-` rows exist yet, so this never fires.

    Idempotent: a re-run finds no `guest-` rows to match.
    """
    Person = apps.get_model("accounts", "Person")
    Guest = apps.get_model("reservations", "Guest")

    for person in Person.objects.filter(legacy_id__startswith=_GUEST_PREFIX).iterator():
        suffix = person.legacy_id[len(_GUEST_PREFIX) :]
        if not suffix.isdigit():
            # Malformed mirror key — leave it untouched (mirrors 0034).
            continue
        gid = int(suffix)
        guest = Guest.objects.filter(pk=gid).first()
        if guest is not None and guest.legacy_id:
            new_legacy_id = f"{_CLIENT_PREFIX}{guest.legacy_id}"
            # Fail closed on collision: another Person already carries this
            # client key. Do NOT mint a silent duplicate.
            if Person.objects.filter(legacy_id=new_legacy_id).exclude(pk=person.pk).exists():
                raise RuntimeError(
                    "GAP-045 D5-4c re-key collision: a Person already has "
                    f"legacy_id={new_legacy_id!r} (re-keying guest mirror "
                    f"Person pk={person.pk}, legacy_id={person.legacy_id!r}). "
                    "Either a ClientLoader run wrote client- rows before this "
                    "migration (run the migration before loadlegacy), or two "
                    "legacy Guests share a VillaClientDetails id (duplicate "
                    "source legacy_id) and must be de-duplicated before re-keying."
                )
        else:
            new_legacy_id = None
        person.legacy_id = new_legacy_id
        person.save(update_fields=["legacy_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_person_kind"),
        ("reservations", "0034_person_authoritative"),
    ]

    operations = [
        migrations.RunPython(_rekey_forward, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="guestpreference",
            name="guest",
        ),
        migrations.RemoveField(
            model_name="booking",
            name="guest",
        ),
        migrations.RemoveField(
            model_name="quotation",
            name="guest",
        ),
        migrations.RemoveField(
            model_name="bookingguest",
            name="guest",
        ),
        migrations.RemoveField(
            model_name="enquiry",
            name="guest",
        ),
        migrations.DeleteModel(
            name="Guest",
        ),
    ]
