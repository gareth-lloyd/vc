"""Re-sync the charge-itemisation templates (GAP-018).

The booking confirmation and the deposit/balance payment-request emails now
render an itemised charge breakdown (snapshot subtotal + charge lines + a
separate Discounts block + grand total) against the new `charge_breakdown`
context key. `sync_templates` versions each changed template (deactivates the
old row, activates the new) — a pure content bump reading the current on-disk
bodies. Reverse is a no-op; the superseded versions stay inactive.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _forwards(apps: Any, schema_editor: Any) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates(model=apps.get_model("comms", "EmailTemplate"))


class Migration(migrations.Migration):
    dependencies = [
        ("comms", "0014_per_line_currency_quotation_sent"),
    ]

    operations = [
        migrations.RunPython(_forwards, migrations.RunPython.noop),
    ]
