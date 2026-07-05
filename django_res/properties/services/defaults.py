"""Creation-time snapshot of the global `PropertyDefaults` (GAP-070).

Copies the singleton's values into concrete `PropertySettings` /
`PropertyFinance` rows when a property is created (API create and
`:duplicate`). After the snapshot the rows are plain, independently-editable
attributes — changing a global default never re-flows into existing
properties. `get_or_create` semantics: an existing row is never clobbered.
"""

from __future__ import annotations

from properties.models import PropertyDefaults, PropertyFinance, PropertySettings
from properties.models.property import Property

_SETTINGS_FIELDS = (
    "availability_default",
    "bookings_require_pre_approval",
    "requires_enquiry_first",
    "currency",
    "check_in_time",
    "check_out_time",
    "changeover_day",
    "min_nights_rental",
    "min_nights_rental_note",
    "prices_entered_as",
    "hold_duration_hours",
)

# Finance *policy* only — per-owner data (contact, bank_*, tax_number) has no
# global default by design and stays blank until the operator fills it in.
_FINANCE_FIELDS = (
    "commission_calculation_type",
    "commission_amount",
    "commission_note",
    "tax_is_exempt",
    "tax_percentage",
    "deposit_required",
    "deposit_calculation_type",
    "deposit_amount",
    "interim_required",
    "interim_calculation_type",
    "interim_amount",
    "days_interim_due_before_arrival",
    "days_balance_due_before_arrival",
    "security_deposit_required",
    "security_deposit_calculation_type",
    "security_deposit_amount",
    "security_deposit_days_due_before_arrival",
    "security_deposit_days_refunded_after_departure",
    "security_deposit_payment_method",
    "cancellation_fee_amount",
    "cancellation_fee_percent",
    "cancellation_window_days",
    "cancellation_notes",
)


def snapshot_defaults(property: Property) -> None:
    """Materialise settings + finance rows for `property` from the singleton."""
    source = PropertyDefaults.get_solo()
    PropertySettings.objects.get_or_create(
        property=property,
        defaults={field: getattr(source, field) for field in _SETTINGS_FIELDS},
    )
    PropertyFinance.objects.get_or_create(
        property=property,
        defaults={field: getattr(source, field) for field in _FINANCE_FIELDS},
    )
