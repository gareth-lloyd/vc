"""Backfill `BookingHold.quotation_line` for holds created before the FK existed.

Holds placed by the pre-FK code carry `quotation` but not `quotation_line`. Once
`QuotationService.sync_line_hold` ships, editing such a line can't find its hold
(the FK is NULL) and would place a *second* hold — so link each orphaned hold to
its line by the natural key it was placed on: (quotation, property, dates).
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _link_holds_to_lines(apps: Any, schema_editor: Any) -> None:
    BookingHold = apps.get_model("reservations", "BookingHold")
    QuotationLine = apps.get_model("reservations", "QuotationLine")

    orphans = BookingHold.objects.filter(
        quotation__isnull=False,
        quotation_line__isnull=True,
    )
    for hold in orphans.iterator():
        matches = list(
            QuotationLine.objects.filter(
                quotation_id=hold.quotation_id,
                property_id=hold.property_id,
                date_from=hold.date_from,
                date_to=hold.date_to,
            )[:2]
        )
        # Only link when the (quotation, property, dates) key is unambiguous;
        # a tie means we can't tell which line owns the hold, so leave it NULL.
        if len(matches) == 1:
            hold.quotation_line = matches[0]
            hold.save(update_fields=["quotation_line"])


def _noop(apps: Any, schema_editor: Any) -> None:
    """Reverse is a no-op: clearing the link would re-create the orphan bug."""


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0025_bookinghold_quotation_line"),
    ]

    operations = [
        migrations.RunPython(_link_holds_to_lines, _noop),
    ]
