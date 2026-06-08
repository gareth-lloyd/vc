"""Seed initial EmailTemplate rows from the on-disk template files.

The seed deliberately uses the live ``comms.management.commands.seed_email_templates.sync_templates``
function rather than ``apps.get_model`` because templates need their MJML
compiled to HTML, which is performed by the live model's ``save()`` override.
If the EmailTemplate save signature ever changes incompatibly, this
migration will need a custom in-place implementation; until then the live
function is the single source of seed truth.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _forwards(apps: Any, schema_editor: Any) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates(model=apps.get_model("comms", "EmailTemplate"))


def _backwards(apps: Any, schema_editor: Any) -> None:
    EmailTemplate = apps.get_model("comms", "EmailTemplate")
    EmailTemplate.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0002_email_template_mjml"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards),
    ]
