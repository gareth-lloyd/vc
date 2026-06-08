"""Seed reminder templates used by `payments.tasks.send_payment_reminders`."""

from __future__ import annotations

from typing import Any

from django.db import migrations


REMINDER_KEYS = [
    "payment.reminder.deposit",
    "booking.balance_reminder_7d",
    "booking.balance_reminder_3d",
    "booking.balance_due_today",
    "payment.security_deposit_request",
]


def _forwards(apps: Any, schema_editor: Any) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates(model=apps.get_model("comms", "EmailTemplate"))


def _backwards(apps: Any, schema_editor: Any) -> None:
    EmailTemplate = apps.get_model("comms", "EmailTemplate")
    EmailTemplate.objects.filter(key__in=REMINDER_KEYS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0005_seed_payment_templates"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards),
    ]
