"""Seed the `ical.conflict` template (iCal-import commitment-clash ops alert).

Load-bearing: the GAP-011 poller fires `ical_conflict_detected`, whose comms
handler sends via `_safe_send`, which *swallows* `EmailTemplateNotFound`.
Without this row a conflict would silently email no one, so the template ships
with the feature.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations

ICAL_KEYS = ["ical.conflict"]


def _forwards(apps: Any, schema_editor: Any) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates(model=apps.get_model("comms", "EmailTemplate"))


def _backwards(apps: Any, schema_editor: Any) -> None:
    EmailTemplate = apps.get_model("comms", "EmailTemplate")
    EmailTemplate.objects.filter(key__in=ICAL_KEYS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0011_emailtemplate_title_drop_body_template"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards),
    ]
