"""GAP-059: `RatePeriod.name` becomes a compulsory operator label.

Ordered ops: backfill every blank name with the deterministic date-span
placeholder, then tighten the field and add the CHECK. The formatter is an
inline copy of `pricing.services.period_names.derive_period_name` (migrations
don't import app code — the module may drift after this file is frozen).

Reverse: drop the constraint and re-relax the field; backfilled names stay —
they're valid data.

Deploy note: the migration is atomic, but a blank-name INSERT committed by
still-running old code between the backfill and the AddConstraint fails the
whole migration loudly (constraint validation). Single-operator app — run in
a quiet window.

Audit note: `name` is an audit-tracked field, but historical models dispatch
no signals, so the backfill writes no AuditLog rows — deliberate: these are
placeholder labels minted by the system, not operator edits.
"""

from django.conf import settings
from django.db import migrations, models

_MONTHS_ABBR = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)  # fmt: skip

_EN_DASH = "\u2013"


def _derive_period_name(date_from, date_to):
    from_month = _MONTHS_ABBR[date_from.month - 1]
    to_month = _MONTHS_ABBR[date_to.month - 1]
    if date_from.year != date_to.year:
        return (
            f"{date_from.day} {from_month} {date_from.year}"
            f"{_EN_DASH}{date_to.day} {to_month} {date_to.year}"
        )
    if date_from.month != date_to.month:
        return f"{date_from.day} {from_month}{_EN_DASH}{date_to.day} {to_month}"
    if date_from.day != date_to.day:
        return f"{date_from.day}{_EN_DASH}{date_to.day} {from_month}"
    return f"{date_from.day} {from_month}"


def backfill_blank_names(apps, schema_editor):
    """Name every blank period from its date span.

    `.strip()` catches whitespace-only rows the `<> ''` CHECK would otherwise
    let survive unnamed forever. Row-at-a-time save is fine at this table's
    scale (hundreds of periods) and keeps the derivation in one place.
    """
    RatePeriod = apps.get_model("pricing", "RatePeriod")
    for period in RatePeriod.objects.all().only("id", "name", "date_from", "date_to"):
        if period.name.strip() == "":
            period.name = _derive_period_name(period.date_from, period.date_to)
            period.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0016_rename_raterule_to_rateband"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(backfill_blank_names, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="rateperiod",
            name="name",
            field=models.CharField(max_length=128),
        ),
        migrations.AddConstraint(
            model_name="rateperiod",
            constraint=models.CheckConstraint(
                condition=models.Q(("name", ""), _negated=True),
                name="rateperiod_name_not_blank",
            ),
        ),
    ]
