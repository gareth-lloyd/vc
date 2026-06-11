"""Customer-facing value formatting shared across apps.

Mirrors the `_money()` precedent in `reservations.services.quotation_render`:
context builders hand templates pre-formatted strings so every consumer
(live send, operator preview) renders identically.
"""

from __future__ import annotations

import datetime

from django.utils import timezone
from django.utils.formats import date_format


def format_date(value: datetime.date) -> str:
    """Long-form customer-facing date, e.g. ``8 July 2025``.

    Accepts a ``date`` or ``datetime``; the time component is dropped —
    guests read stay dates and expiry as days. Aware datetimes are
    converted to the project timezone first so the calendar date is
    right near midnight.
    """
    if isinstance(value, datetime.datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    return date_format(value, "j F Y")
