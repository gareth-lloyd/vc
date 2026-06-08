from __future__ import annotations

from django.db import migrations, models


def _humanize_key(key: str) -> str:
    """Derive a human-facing title from a dotted key.

    ``booking.confirmation`` -> ``Booking Confirmation``;
    ``owner.block_contested`` -> ``Owner Block Contested``.
    """
    return key.replace(".", " ").replace("_", " ").title()


def backfill_titles(apps, schema_editor):
    EmailTemplate = apps.get_model("comms", "EmailTemplate")
    for template in EmailTemplate.objects.all():
        template.title = _humanize_key(template.key)
        template.save(update_fields=["title"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0010_seed_owner_block_contested_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailtemplate",
            name="title",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_titles, noop_reverse),
        migrations.RemoveField(
            model_name="emailtemplate",
            name="body_template",
        ),
    ]
