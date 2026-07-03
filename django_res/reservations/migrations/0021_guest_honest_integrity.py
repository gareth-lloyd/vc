"""Guest honest-integrity: optional email, E.164 phones, ACTIVE-only CHECKs.

Triage gates the constraint add — see django_res_design/design/history/people-model-cleanup.md
(Migration ordering). The data ops here operate only on rows the rebuild already
wrote to Postgres; the legacy-cutover loaders produce clean data at import and
never need the `@noemail.local` scrub.
"""

from __future__ import annotations

import core.fields
from django.conf import settings
from django.db import migrations, models


def scrub_synthetic_emails(apps, schema_editor):
    """Collapse non-real emails to NULL before the contactability CHECK lands.

    Two cases: the `enquiry-{id}@noemail.local` synthetic the rebuild fabricated,
    and any empty-string email (the absence of an email, not a present-but-blank
    one). Both must be NULL so `email__isnull` — which the constraint and the
    `disposition_channelless` triage below key on — reflects the truth.
    """
    Guest = apps.get_model("reservations", "Guest")
    Guest.objects.filter(email__endswith="@noemail.local").update(email=None)
    Guest.objects.filter(email="").update(email=None)


def normalize_phones(apps, schema_editor):
    """One-time E.164 pass; loaders normalize on future import."""
    from reservations.phone import to_e164

    Guest = apps.get_model("reservations", "Guest")
    for guest in Guest.objects.exclude(phone="").iterator():
        normalized = to_e164(guest.phone)
        if normalized != guest.phone:
            guest.phone = normalized
            guest.save(update_fields=["phone"])


def disposition_channelless(apps, schema_editor):
    """ACTIVE guest with no channel can't be contactable — archive (honest)."""
    Guest = apps.get_model("reservations", "Guest")
    Guest.objects.filter(status="active", email__isnull=True, phone="").update(status="archived")


def reconcile_preferences(apps, schema_editor):
    """Drop an unactionable stated preference on the remaining ACTIVE rows."""
    Guest = apps.get_model("reservations", "Guest")
    Guest.objects.filter(status="active", contact_method="email", email__isnull=True).update(
        contact_method=None
    )
    Guest.objects.filter(status="active", contact_method__in=["phone", "sms"], phone="").update(
        contact_method=None
    )


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0013_propertylocation_timezone"),
        ("reservations", "0020_owner_block_feed"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Schema: email becomes optional (no constraint yet).
        migrations.AlterField(
            model_name="guest",
            name="email",
            field=core.fields.CIEmailField(blank=True, db_index=True, max_length=254, null=True),
        ),
        # 2-5. Data triage — gates the constraint add.
        migrations.RunPython(scrub_synthetic_emails, migrations.RunPython.noop),
        migrations.RunPython(normalize_phones, migrations.RunPython.noop),
        migrations.RunPython(disposition_channelless, migrations.RunPython.noop),
        migrations.RunPython(reconcile_preferences, migrations.RunPython.noop),
        # 6. Schema: the honest-NOT-NULL constraints, now that data is clean.
        migrations.AddConstraint(
            model_name="guest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "active"), _negated=True),
                    ("email__isnull", False),
                    models.Q(("phone", ""), _negated=True),
                    _connector="OR",
                ),
                name="guest_active_contactable",
            ),
        ),
        migrations.AddConstraint(
            model_name="guest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "active"), _negated=True),
                    models.Q(
                        models.Q(
                            models.Q(("contact_method", "email"), _negated=True),
                            ("email__isnull", False),
                            _connector="OR",
                        ),
                        models.Q(
                            models.Q(("contact_method__in", ["phone", "sms"]), _negated=True),
                            models.Q(("phone", ""), _negated=True),
                            _connector="OR",
                        ),
                    ),
                    _connector="OR",
                ),
                name="guest_active_preference_actionable",
            ),
        ),
    ]
