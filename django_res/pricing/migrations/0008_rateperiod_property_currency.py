"""GAP-110 U1 (expand): denormalise the regime key onto `RatePeriod`.

`RatePeriod.property` / `.currency` mirror the owning plan so the regime-wide
no-overlap EXCLUDE (`pricing/0010`) can partition on them — Postgres can't
join through `plan` inside a constraint. Added nullable here and backfilled;
`pricing/0009` makes them NOT NULL and indexes them. Two migrations because
an UPDATE followed by `SET NOT NULL` in one transaction fails with "pending
trigger events" on any populated table (deferred FK checks).

Audit note (the sanctioned `RunPython` exception): the backfill is a
`queryset.update()` on a tracked model. Historical models carry no signal
receivers, the columns are derived (not tracked), and this migration is its
own trail.
"""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def backfill_regime(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    """Stamp every period's `property` / `currency` from its plan."""
    RatePlan = apps.get_model("pricing", "RatePlan")
    RatePeriod = apps.get_model("pricing", "RatePeriod")
    owner = RatePlan.objects.filter(pk=OuterRef("plan_id"))
    RatePeriod.objects.update(
        property_id=Subquery(owner.values("property_id")[:1]),
        currency_id=Subquery(owner.values("currency_id")[:1]),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0007_extra_idempotency_key_and_more"),
        ("properties", "0007_description_other_information"),
    ]

    operations = [
        migrations.AddField(
            model_name="rateperiod",
            name="currency",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rate_periods",
                to="pricing.currency",
            ),
        ),
        migrations.AddField(
            model_name="rateperiod",
            name="property",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rate_periods",
                to="properties.property",
            ),
        ),
        migrations.RunPython(backfill_regime, migrations.RunPython.noop),
    ]
