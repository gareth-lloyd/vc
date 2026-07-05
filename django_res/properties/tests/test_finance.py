from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType

from core.models import AuditLog
from properties.enums import (
    CommissionCalcType,
    DepositCalcType,
    SecurityDepositCalcType,
    SecurityDepositPaymentMethod,
)
from properties.models import (
    GroupFinance,
    Property,
    PropertyCategory,
    PropertyFinance,
    PropertyGroup,
    Region,
)
from properties.models.geo import Country


@pytest.fixture
def category(db: None) -> PropertyCategory:
    return PropertyCategory.objects.create(name="Villa", slug="villa")


@pytest.fixture
def country(db: None) -> Country:
    country, _ = Country.objects.get_or_create(
        iso2="GB",
        defaults={"name": "United Kingdom", "iso3": "GBR"},
    )
    return country


@pytest.fixture
def region(country: Country) -> Region:
    return Region.objects.create(country=country, name="Cornwall", slug="cornwall")


@pytest.fixture
def group(db: None) -> PropertyGroup:
    return PropertyGroup.objects.create(name="Finance test group")


@pytest.fixture
def prop(
    group: PropertyGroup,
    category: PropertyCategory,
    region: Region,
) -> Property:
    return Property.objects.create(
        name="Sea View",
        display_name="Sea View",
        slug="sea-view-finance",
        group=group,
        category=category,
        region=region,
    )


@pytest.mark.django_db
def test_property_group_post_save_creates_group_finance() -> None:
    group = PropertyGroup.objects.create(name="Auto-finance group")

    assert GroupFinance.objects.filter(group=group).exists()
    gf = group.finance
    # Sensible non-null defaults are applied.
    assert gf.commission_calculation_type == CommissionCalcType.PERCENT
    assert gf.commission_amount == Decimal("0.00")
    assert gf.tax_is_exempt is False
    assert gf.deposit_required is True
    assert gf.deposit_calculation_type == DepositCalcType.PERCENT
    assert gf.deposit_amount == Decimal("30.00")
    assert gf.days_balance_due_before_arrival == 60
    assert gf.security_deposit_required is False
    assert gf.security_deposit_payment_method == SecurityDepositPaymentMethod.CARD_HOLD
    assert gf.security_deposit_calculation_type == SecurityDepositCalcType.FIXED
    assert gf.cancellation_window_days == 0


@pytest.mark.django_db
def test_property_group_resave_does_not_replace_group_finance() -> None:
    group = PropertyGroup.objects.create(name="Stable finance")
    finance_pk = group.finance.pk

    group.description = "Updated"
    group.save()

    group.refresh_from_db()
    assert group.finance.pk == finance_pk


# --- effective_*() resolvers (GAP-070): own fields + policy-floor fallbacks --
#
# Post-freeze (migration 0027) real rows carry concrete values; a NULL only
# occurs on rows created outside `snapshot_defaults` (factories, lazy
# `get_or_create`) and resolves to the pre-GAP-070 policy-floor default.
# Group-level values are never consulted.


@pytest.mark.django_db
def test_effective_commission_returns_property_value_when_set(prop: Property) -> None:
    # Group values must be IGNORED — the resolver reads own fields only.
    gf = prop.group.finance
    gf.commission_calculation_type = CommissionCalcType.PERCENT
    gf.commission_amount = Decimal("15.00")
    gf.commission_note = "group note"
    gf.save()

    PropertyFinance.objects.create(
        property=prop,
        commission_calculation_type=CommissionCalcType.FIXED,
        commission_amount=Decimal("100.00"),
        commission_note="property override",
    )

    result = prop.finance.effective_commission()
    assert result == {
        "calculation_type": CommissionCalcType.FIXED,
        "amount": Decimal("100.00"),
        "note": "property override",
    }


@pytest.mark.django_db
def test_effective_commission_null_falls_back_to_policy_floor(prop: Property) -> None:
    """NULL columns resolve to the policy floor, NOT the group's values."""
    gf = prop.group.finance
    gf.commission_calculation_type = CommissionCalcType.FIXED
    gf.commission_amount = Decimal("12.50")
    gf.commission_note = "group default"
    gf.save()

    PropertyFinance.objects.create(property=prop)  # All fields null/blank.

    result = prop.finance.effective_commission()
    assert result == {
        "calculation_type": CommissionCalcType.PERCENT,
        "amount": Decimal("0"),
        "note": "",
    }


@pytest.mark.django_db
def test_effective_commission_empty_note_is_a_real_value(prop: Property) -> None:
    """An empty-string note is a genuine own value (post-freeze semantics) —
    it is returned as-is, never resolved elsewhere."""
    # Group values are inert — seeded only as contrast (pre-GAP-070 a blank
    # note inherited "group note when prop blank"; now it must stay "").
    gf = prop.group.finance
    gf.commission_note = "group note when prop blank"
    gf.commission_amount = Decimal("9.00")
    gf.save()

    PropertyFinance.objects.create(
        property=prop,
        commission_note="",  # blank text stays blank
        commission_amount=None,  # null numeric → policy floor 0
    )

    result = prop.finance.effective_commission()
    assert result["note"] == ""
    assert result["amount"] == Decimal("0")


@pytest.mark.django_db
def test_effective_tax_policy_merges_own_values_and_floor(prop: Property) -> None:
    PropertyFinance.objects.create(
        property=prop,
        tax_percentage=Decimal("5.00"),  # own value
        # tax_is_exempt left null → floor False
        # tax_number left blank → "" (a real value)
    )

    result = prop.finance.effective_tax_policy()
    assert result == {
        "tax_number": "",
        "is_exempt": False,
        "percentage": Decimal("5.00"),
    }


@pytest.mark.django_db
def test_effective_payment_schedule_returns_full_dict(prop: Property) -> None:
    PropertyFinance.objects.create(
        property=prop,
        deposit_amount=Decimal("40.00"),  # own value
        interim_required=True,
        interim_amount=Decimal("50.00"),
        days_interim_due_before_arrival=90,
    )

    result = prop.finance.effective_payment_schedule()
    assert result == {
        "deposit_required": True,  # floor
        "deposit_calculation_type": DepositCalcType.PERCENT,  # floor
        "deposit_amount": Decimal("40.00"),
        "interim_required": True,
        "interim_calculation_type": DepositCalcType.PERCENT,  # floor
        "interim_amount": Decimal("50.00"),
        "days_interim_due_before_arrival": 90,
        "days_balance_due_before_arrival": 60,  # floor
    }


@pytest.mark.django_db
def test_effective_security_deposit_policy_returns_full_dict(prop: Property) -> None:
    PropertyFinance.objects.create(
        property=prop,
        security_deposit_required=True,
        security_deposit_amount=Decimal("1000.00"),
        security_deposit_payment_method=SecurityDepositPaymentMethod.BANK_TRANSFER,
    )

    result = prop.finance.effective_security_deposit_policy()
    assert result == {
        "required": True,
        "calculation_type": SecurityDepositCalcType.FIXED,  # floor
        "amount": Decimal("1000.00"),
        "days_due_before_arrival": 14,  # floor
        "days_refunded_after_departure": 7,  # floor
        "payment_method": SecurityDepositPaymentMethod.BANK_TRANSFER,
    }


@pytest.mark.django_db
def test_effective_cancellation_policy_returns_fields(prop: Property) -> None:
    PropertyFinance.objects.create(
        property=prop,
        cancellation_fee_percent=Decimal("50.00"),
        cancellation_window_days=30,
    )

    result = prop.finance.effective_cancellation_policy()
    assert result == {
        "fee_amount": Decimal("0"),  # floor
        "fee_percent": Decimal("50.00"),
        "window_days": 30,
        "notes": "",
    }


@pytest.mark.django_db
def test_property_finance_bank_iban_round_trips_through_encryption(prop: Property) -> None:
    finance = PropertyFinance.objects.create(
        property=prop,
        bank_iban="GB29 NWBK 6016 1331 9268 19",
    )

    finance.refresh_from_db()
    assert finance.bank_iban == "GB29 NWBK 6016 1331 9268 19"


@pytest.mark.django_db
def test_audit_log_row_emitted_when_commission_amount_changes(prop: Property) -> None:
    finance = PropertyFinance.objects.create(
        property=prop,
        commission_amount=Decimal("10.00"),
    )
    ct = ContentType.objects.get_for_model(PropertyFinance)

    AuditLog.objects.filter(content_type=ct, object_id=str(finance.pk)).delete()

    finance.commission_amount = Decimal("12.00")
    finance.save()

    logs = list(AuditLog.objects.filter(content_type=ct, object_id=str(finance.pk)))
    assert len(logs) == 1
    diff = logs[0].field_diffs
    assert "commission_amount" in diff
    old, new = diff["commission_amount"]
    assert str(old) == "10.00"
    assert str(new) == "12.00"


@pytest.mark.django_db
def test_audit_log_redacts_bank_iban_diff(prop: Property) -> None:
    finance = PropertyFinance.objects.create(
        property=prop,
        bank_iban="GB29 NWBK 6016 1331 9268 19",
    )
    ct = ContentType.objects.get_for_model(PropertyFinance)

    AuditLog.objects.filter(content_type=ct, object_id=str(finance.pk)).delete()

    finance.bank_iban = "GB82 WEST 1234 5698 7654 32"
    finance.save()

    logs = list(AuditLog.objects.filter(content_type=ct, object_id=str(finance.pk)))
    assert len(logs) == 1
    diff = logs[0].field_diffs
    assert "bank_iban" in diff
    old, new = diff["bank_iban"]
    # The fact of the change is recorded; cleartext values are redacted.
    assert old == "[REDACTED]"
    assert new == "[REDACTED]"
