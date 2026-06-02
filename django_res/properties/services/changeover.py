"""ChangeoverService — resolve a property's changeover day and align arrivals.

`AVAILABILITY.CHANGEOVER`. Resolution order for the arrival date:

1. A `ChangeOverRule` whose `[starts_on, ends_on]` window contains the
   arrival date (peak-season override).
2. Otherwise the canonical `PropertySettings.effective("changeover_day")`
   chain (property value, falling back to the group default). When no
   `PropertySettings` row exists, fall straight back to the group default
   (`GroupSettings.changeover_day`, which is non-null and defaults to
   `any`).

`PrefilledChangeOverDay.ANY` means "no constraint". A non-conforming arrival
is never rejected — `align_forward` nudges it to the next valid changeover day
(GAP-007, matching legacy `ResService.cs:2028-2041`).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from properties.enums import PrefilledChangeOverDay
from properties.models.settings import PropertySettings

if TYPE_CHECKING:
    from properties.models import Property

# PrefilledChangeOverDay code -> date.weekday() (Mon=0 .. Sun=6).
_WEEKDAY = {
    PrefilledChangeOverDay.MON.value: 0,
    PrefilledChangeOverDay.TUE.value: 1,
    PrefilledChangeOverDay.WED.value: 2,
    PrefilledChangeOverDay.THU.value: 3,
    PrefilledChangeOverDay.FRI.value: 4,
    PrefilledChangeOverDay.SAT.value: 5,
    PrefilledChangeOverDay.SUN.value: 6,
}


class ChangeoverService:
    """Resolve the effective changeover day and align arrivals forward."""

    @staticmethod
    def effective_day(property: Property, on_date: date) -> str:
        rule = (
            property.changeover_rules.filter(
                starts_on__lte=on_date,
                ends_on__gte=on_date,
            )
            .order_by("starts_on")
            .first()
        )
        if rule is not None:
            return rule.day

        try:
            return property.settings.effective("changeover_day")
        except PropertySettings.DoesNotExist:
            return property.group.settings.changeover_day

    @classmethod
    def required_weekday(cls, property: Property, on_date: date) -> int | None:
        """The property's required changeover weekday on `on_date`.

        Returns a `date.weekday()` int (Mon=0..Sun=6), or `None` when the
        effective day is `any` / unconstrained.
        """
        return _WEEKDAY.get(cls.effective_day(property, on_date))

    @staticmethod
    def align_forward(
        allowed_weekdays: set[int],
        date_from: date,
        date_to: date,
    ) -> tuple[date, date, date | None]:
        """Advance `date_from` to the next allowed changeover weekday.

        Legacy silently nudged a non-conforming arrival forward to the next
        valid changeover day (`ResService.cs:2028-2041`). We preserve the
        requested night count by shifting `date_to` by the same delta (legacy
        kept `date_to` fixed, silently shortening the stay — we don't).

        Returns `(new_from, new_to, shifted_from)` where `shifted_from` is the
        original `date_from` when a shift happened, else `None`. No shift when
        the allowed set is empty or the arrival is already valid.
        """
        if not allowed_weekdays or date_from.weekday() in allowed_weekdays:
            return date_from, date_to, None
        for delta in range(1, 8):
            if (date_from + timedelta(days=delta)).weekday() in allowed_weekdays:
                return (
                    date_from + timedelta(days=delta),
                    date_to + timedelta(days=delta),
                    date_from,
                )
        return date_from, date_to, None  # unreachable: a 7-day window covers every weekday
