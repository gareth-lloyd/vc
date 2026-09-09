"""Seed the `booking.contract` EmailTemplate (GAP-094).

Template bodies live in the DB, so a new (or edited) on-disk
`comms/templates/comms/*` file needs a companion sync migration — otherwise
a deployed environment has no active row for the key and every send raises
`EmailTemplateNotFound` (which the receiver degrades to a logged skip, i.e. a
contract that silently never reaches the guest).
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _forwards(apps: Any, schema_editor: Any) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates(model=apps.get_model("comms", "EmailTemplate"))


def _backwards(apps: Any, schema_editor: Any) -> None:
    # Mirrors 0002/0003: the previous body is not retained and re-running the
    # sync would only re-seed the current on-disk files. No-op by design.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0003_seed_quotation_geo_groups"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards),
    ]
