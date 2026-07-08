"""Seed all EmailTemplate rows from the on-disk template files.

Uses the live ``comms.management.commands.seed_email_templates.sync_templates``
(rather than ``apps.get_model`` alone) because templates need their MJML
compiled to HTML by the live model's ``save()`` override. This collapses the
whole historical 0003→0015 template-seed chain into one idempotent sync from
``comms/templates/comms/*``. If the EmailTemplate save signature ever changes
incompatibly, this migration will need a frozen in-place implementation; until
then the live function is the single source of seed truth.
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
        ("comms", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards),
    ]
