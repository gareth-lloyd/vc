"""Owner blocks are created already APPROVED.

Drops the review-flow fields (a block no longer passes through a staff queue)
and narrows the status enum to APPROVED / CANCELLED. Any stray PENDING/DECLINED
rows (dev/seed data, pre-cutover) never placed a hold, so they fold to
CANCELLED — they never occupied the calendar.
"""

from __future__ import annotations

from django.db import migrations, models


def _fold_legacy_statuses(apps, schema_editor):
    OwnerBlock = apps.get_model("reservations", "OwnerBlock")
    OwnerBlock.objects.filter(status__in=("pending", "declined")).update(status="cancelled")


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0018_reconcile_owner_block_indexes"),
    ]

    operations = [
        migrations.RunPython(_fold_legacy_statuses, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="ownerblock",
            name="review_note",
        ),
        migrations.RemoveField(
            model_name="ownerblock",
            name="reviewed_at",
        ),
        migrations.RemoveField(
            model_name="ownerblock",
            name="reviewed_by",
        ),
        migrations.AlterField(
            model_name="ownerblock",
            name="status",
            field=models.CharField(
                choices=[("approved", "Approved"), ("cancelled", "Cancelled")],
                default="approved",
                max_length=16,
            ),
        ),
    ]
