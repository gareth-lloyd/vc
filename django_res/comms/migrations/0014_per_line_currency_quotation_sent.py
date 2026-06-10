"""Re-sync `quotation.sent` for per-line currency (GAP-014).

The header-level `currency_code` left the render context when currency moved
to each line, so the seeded template rendered "Total ()" and currency-less
discount notes. The template now renders `line.currency_code` per line — a
mixed GBP/EUR quote shows each option in its own currency. `sync_templates`
versions the template (deactivates the old row, activates the new), so this
is a pure content bump; reverse is a no-op — the superseded version stays
inactive.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _forwards(apps: Any, schema_editor: Any) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates(model=apps.get_model("comms", "EmailTemplate"))


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0013_drop_quotation_grand_total"),
    ]

    operations = [
        migrations.RunPython(_forwards, migrations.RunPython.noop),
    ]
