"""Seed payment / security-deposit lifecycle templates added in PR 2."""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _forwards(apps: Any, schema_editor: Any) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates()


def _backwards(apps: Any, schema_editor: Any) -> None:
    EmailTemplate = apps.get_model("comms", "EmailTemplate")
    EmailTemplate.objects.filter(
        key__in=[
            "payment.receipt",
            "payment.failed",
            "payment.failed_guest",
            "security_deposit.released",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0004_seed_lifecycle_templates"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards),
    ]
