"""Seed the `owner_block.contested` template (owner-block contest notification).

Load-bearing: `OwnerBlockService.contest` fires a signal whose comms handler
sends via `_safe_send`, which *swallows* `EmailTemplateNotFound`. Without this
row a contest would silently email no one, so the template ships with the
feature.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations

OWNER_BLOCK_KEYS = ["owner_block.contested"]


def _forwards(apps: Any, schema_editor: Any) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates(model=apps.get_model("comms", "EmailTemplate"))


def _backwards(apps: Any, schema_editor: Any) -> None:
    EmailTemplate = apps.get_model("comms", "EmailTemplate")
    EmailTemplate.objects.filter(key__in=OWNER_BLOCK_KEYS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0009_alter_emaillog_status"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards),
    ]
