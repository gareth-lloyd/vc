"""GAP-070 freeze-before-drop: resolve group inheritance into concrete values.

For EVERY property, run the old `effective()` resolution one final time and
store the result on `PropertySettings`/`PropertyFinance` (creating missing
rows — legacy properties without a VillaFinance row have no finance row at
all). NOTE: for row-less properties this deliberately ACTIVATES the group
floor that some consumers (engine/scheduler/charges short-circuit on a missing
finance row) never applied — that "no policy" state was the gap GAP-070's
review B1 identified, and decision 7 confirms these villas should carry their
group/owner defaults. Resolution contract (mirrors the deleted `effective()`): own value wins
unless NULL or ""; otherwise the group row's value is written in. A NULL group
value stays NULL (decision 2 — no backfill-to-global). Must run while the
group tables still exist; the next schema migration drops them.

Per-owner group data (contact, bank_*, tax_number) IS frozen — the GroupFinance
rows carry real mirrored owner bank/commission/contact values that properties
currently observe through `effective()`.
"""

from django.db import migrations

_SETTINGS_FIELDS = (
    "availability_default",
    "bookings_require_pre_approval",
    "requires_enquiry_first",
    "currency_id",
    "check_in_time",
    "check_out_time",
    "changeover_day",
    "min_nights_rental",
    "min_nights_rental_note",
    "prices_entered_as",
    "hold_duration_hours",
)

_FINANCE_FIELDS = (
    "contact_id",
    "notes",
    "commission_calculation_type",
    "commission_amount",
    "commission_note",
    "tax_number",
    "tax_is_exempt",
    "tax_percentage",
    "bank_account_name",
    "bank_account_number",
    "bank_sort_code",
    "bank_iban",
    "bank_bic",
    "bank_name",
    "bank_address_line_1",
    "bank_address_line_2",
    "bank_post_code",
    "bank_city",
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


def freeze_row(row, group_row, fields):
    """Write the group's value into every NULL/"" field on `row`.

    The old `effective()` treated NULL and "" as "inherit from the group";
    everything else is an own value and wins. Returns True when anything
    changed.
    """
    changed = False
    for field in fields:
        own = getattr(row, field)
        if own is not None and own != "":
            continue
        group_value = getattr(group_row, field)
        if group_value != own:
            setattr(row, field, group_value)
            changed = True
    return changed


def freeze_all(apps, schema_editor):
    Property = apps.get_model("properties", "Property")
    PropertySettings = apps.get_model("properties", "PropertySettings")
    PropertyFinance = apps.get_model("properties", "PropertyFinance")
    GroupSettings = apps.get_model("properties", "GroupSettings")
    GroupFinance = apps.get_model("properties", "GroupFinance")

    settings_by_group = {gs.group_id: gs for gs in GroupSettings.objects.all()}
    finance_by_group = {gf.group_id: gf for gf in GroupFinance.objects.all()}

    for prop in Property.objects.all().iterator():
        settings_row, _ = PropertySettings.objects.get_or_create(property_id=prop.pk)
        group_settings = settings_by_group.get(prop.group_id)
        # A group without a settings/finance row has no floor to inherit —
        # the old effective() had nothing to resolve to; leave values as-is.
        if group_settings and freeze_row(settings_row, group_settings, _SETTINGS_FIELDS):
            settings_row.save()

        finance_row, _ = PropertyFinance.objects.get_or_create(property_id=prop.pk)
        group_finance = finance_by_group.get(prop.group_id)
        if group_finance and freeze_row(finance_row, group_finance, _FINANCE_FIELDS):
            finance_row.save()


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0026_propertydefaults"),
    ]

    operations = [
        migrations.RunPython(freeze_all, migrations.RunPython.noop),
    ]
