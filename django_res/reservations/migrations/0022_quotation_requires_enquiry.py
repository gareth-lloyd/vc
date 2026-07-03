"""Quotation.enquiry becomes mandatory — every quote has an enquiry.

Adds `Enquiry.contact_method` (stated preference, carried onto the Guest on
resolve), back-creates a minimal `AGENT_PORTAL` enquiry for any orphaned
quotation (rebuild data), then tightens `Quotation.enquiry` to PROTECT/NOT NULL.
See django_res_design/design/history/people-model-cleanup.md.
"""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


def backfill_enquiries(apps, schema_editor):
    """Back-create + link a minimal enquiry for every enquiry-less quotation."""
    Quotation = apps.get_model("reservations", "Quotation")
    Enquiry = apps.get_model("reservations", "Enquiry")
    orphans = Quotation.objects.filter(enquiry__isnull=True).select_related("guest")
    for quotation in orphans:
        guest = quotation.guest
        enquiry = Enquiry.objects.create(
            guest=guest,
            first_name=guest.first_name,
            last_name=guest.last_name,
            email=guest.email or "",
            phone=guest.phone,
            contact_method=guest.contact_method,
            agent_id=quotation.agent_id,
            site_source="agent_portal",
            # Enquiry.reference is max_length=32; the "AE-" prefix eats 3. Guard
            # the bound so an unusually long quotation reference (e.g. from the
            # prod snapshot, not the short QVC{n} dev format) can't overflow and
            # abort the migration mid-deploy. Quotation.reference is unique, so
            # the truncated value stays unique for any realistic length.
            reference=f"AE-{quotation.reference}"[:32],
        )
        quotation.enquiry = enquiry
        quotation.save(update_fields=["enquiry"])


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0021_guest_honest_integrity"),
    ]

    operations = [
        migrations.AddField(
            model_name="enquiry",
            name="contact_method",
            field=models.CharField(
                blank=True,
                choices=[("email", "Email"), ("phone", "Phone"), ("sms", "SMS")],
                max_length=8,
                null=True,
            ),
        ),
        # Backfill orphaned quotations before tightening to NOT NULL.
        migrations.RunPython(backfill_enquiries, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="quotation",
            name="enquiry",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="quotations",
                to="reservations.enquiry",
            ),
        ),
    ]
