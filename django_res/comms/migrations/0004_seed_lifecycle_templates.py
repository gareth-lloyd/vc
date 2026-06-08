"""Seed the lifecycle email templates added for booking/quotation/hold events.

Re-uses ``sync_templates`` so any subsequent edit to the on-disk template
files yields a new active version on the next ``migrate`` (the older
version is deactivated rather than mutated).
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _forwards(apps: Any, schema_editor: Any) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates(model=apps.get_model("comms", "EmailTemplate"))


def _backwards(apps: Any, schema_editor: Any) -> None:
    EmailTemplate = apps.get_model("comms", "EmailTemplate")
    EmailTemplate.objects.filter(
        key__in=[
            "booking.declined",
            "booking.cancelled",
            "booking.checked_out",
            "owner.approval_request",
            "hold.expired",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0003_seed_templates"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards),
    ]
