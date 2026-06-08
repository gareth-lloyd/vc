"""Seed `payment.card_update_request` — used by the CC branch of
`payments.tasks.send_payment_reminders`."""

from __future__ import annotations

from typing import Any

from django.db import migrations


CARD_UPDATE_KEY = "payment.card_update_request"


def _forwards(apps: Any, schema_editor: Any) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates(model=apps.get_model("comms", "EmailTemplate"))


def _backwards(apps: Any, schema_editor: Any) -> None:
    EmailTemplate = apps.get_model("comms", "EmailTemplate")
    EmailTemplate.objects.filter(key=CARD_UPDATE_KEY).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0007_unique_email_log_idempotency_hash"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards),
    ]
