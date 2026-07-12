"""Re-sync EmailTemplate rows after the GAP-078 quotation body change.

``quotation.sent.body.mjml`` gained country/region section headers
(``line_groups`` loop). Template bodies live in the DB, so every edit to an
on-disk ``comms/templates/comms/*`` file needs a companion sync migration —
otherwise deployed environments keep serving the stale body.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _forwards(apps: Any, schema_editor: Any) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates(model=apps.get_model("comms", "EmailTemplate"))


def _backwards(apps: Any, schema_editor: Any) -> None:
    # The previous body is not retained; re-running 0002's sync would just
    # re-seed the current on-disk files. Backwards is a no-op by design.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0002_seed_templates"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards),
    ]
