"""ChangeoverService — resolve and enforce a property's changeover day.

`AVAILABILITY.CHANGEOVER.ENFORCE`. Resolution order for the arrival date:

1. A `ChangeOverRule` whose `[starts_on, ends_on]` window contains the
   arrival date (peak-season override).
2. Otherwise the canonical `PropertySettings.effective("changeover_day")`
   chain (property value, falling back to the group default). When no
   `PropertySettings` row exists, fall straight back to the group default
   (`GroupSettings.changeover_day`, which is non-null and defaults to
   `any`).

`PrefilledChangeOverDay.ANY` means "no constraint".
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from core.exceptions import ChangeoverViolation
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
    """Resolve the effective changeover day and validate arrival dates."""

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
    def validate_arrival(
        cls,
        property: Property,
        date_from: date,
        *,
        allow_override: bool = False,
    ) -> None:
        """Raise `ChangeoverViolation` if `date_from` is the wrong weekday.

        No-op when the effective day is `any`, when the arrival already
        lands on the required weekday, or when `allow_override` is set.
        """
        if allow_override:
            return
        day = cls.effective_day(property, date_from)
        required_weekday = _WEEKDAY.get(day)
        if required_weekday is None:  # ANY / unknown -> unconstrained
            return
        if date_from.weekday() != required_weekday:
            required_label = PrefilledChangeOverDay(day).label
            raise ChangeoverViolation(
                f"Arrival {date_from} is not on the property's changeover day "
                f"({required_label}). An explicit override is required to proceed."
            )
