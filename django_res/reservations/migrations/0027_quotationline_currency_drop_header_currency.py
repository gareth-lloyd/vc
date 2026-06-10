# GAP-014: currency moves from the Quotation header to each line (legacy
# parity — `VillaQuotationDetails.CurrencyId`; the master table had none).
# Pre-cutover: the backfill covers dev/staging rows only.
#
# Deliberately irreversible (no RunPython reverse): reversing RemoveField
# would re-add the non-null header FK to a populated table with no data to
# fill it — Django refusing loudly beats a NotNullViolation mid-rollback.

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def backfill_line_currency(apps, schema_editor):
    Quotation = apps.get_model("reservations", "Quotation")
    QuotationLine = apps.get_model("reservations", "QuotationLine")
    QuotationLine.objects.update(
        currency_id=Subquery(
            Quotation.objects.filter(pk=OuterRef("quotation_id")).values("currency_id")[:1]
        )
    )


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0001_initial"),
        ("reservations", "0026_backfill_bookinghold_quotation_line"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotationline",
            name="currency",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="pricing.currency",
            ),
        ),
        migrations.RunPython(backfill_line_currency),
        migrations.AlterField(
            model_name="quotationline",
            name="currency",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="pricing.currency",
            ),
        ),
        migrations.RemoveField(
            model_name="quotation",
            name="currency",
        ),
    ]
