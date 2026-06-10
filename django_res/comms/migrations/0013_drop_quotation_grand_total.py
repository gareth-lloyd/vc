"""Re-sync `quotation.sent` to drop the summed grand-total footer.

Quotation lines are alternative villa options the guest picks ONE of, so a
combined "Total" across them is misleading — the quote-builder cart dropped
its equivalent "Subtotal" for the same reason. `sync_templates` versions the
template (deactivates the old row, activates the new), so this is a pure
content bump; reverse is a no-op — the superseded version stays inactive.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _forwards(apps: Any, schema_editor: Any) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates(model=apps.get_model("comms", "EmailTemplate"))


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0012_seed_ical_conflict_template"),
    ]

    operations = [
        migrations.RunPython(_forwards, migrations.RunPython.noop),
    ]
