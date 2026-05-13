from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType

from core.models import AuditLog
from properties.enums import (
    CommissionCalcType,
    DepositCalcType,
    SecurityDepositCalcFrom,
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
    assert gf.security_deposit_calculate_from == SecurityDepositCalcFrom.TOTAL_STAY
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


@pytest.mark.django_db
def test_effective_commission_returns_property_value_when_set(prop: Property) -> None:
    # Group floor.
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
def test_effective_commission_falls_back_to_group_when_property_null(prop: Property) -> None:
    gf = prop.group.finance
    gf.commission_calculation_type = CommissionCalcType.PERCENT
    gf.commission_amount = Decimal("12.50")
    gf.commission_note = "group default"
    gf.save()

    PropertyFinance.objects.create(property=prop)  # All fields null/blank.

    result = prop.finance.effective_commission()
    assert result == {
        "calculation_type": CommissionCalcType.PERCENT,
        "amount": Decimal("12.50"),
        "note": "group default",
    }


@pytest.mark.django_db
def test_effective_commission_empty_string_field_falls_back_to_group(prop: Property) -> None:
    """Empty string at property level → inherit from group, same as null.

    Exercises both branches of the generic `effective()` resolver:
    `is None` for nullable numerics/booleans, and empty-string fallback
    for `TextField` / `CharField` columns.
    """
    gf = prop.group.finance
    gf.commission_note = "group note when prop blank"
    gf.commission_amount = Decimal("9.00")
    gf.save()

    PropertyFinance.objects.create(
        property=prop,
        commission_note="",  # explicit blank text → inherit
        commission_amount=None,  # explicit null numeric → inherit
    )

    result = prop.finance.effective_commission()
    assert result["note"] == "group note when prop blank"
    assert result["amount"] == Decimal("9.00")


@pytest.mark.django_db
def test_effective_tax_policy_returns_merged_dict(prop: Property) -> None:
    gf = prop.group.finance
    gf.tax_number = "GROUP-TAX-1"
    gf.tax_is_exempt = False
    gf.tax_percentage = Decimal("20.00")
    gf.save()

    PropertyFinance.objects.create(
        property=prop,
        tax_percentage=Decimal("5.00"),  # override
        # tax_is_exempt left null → inherit
        # tax_number left blank → inherit
    )

    result = prop.finance.effective_tax_policy()
    assert result == {
        "tax_number": "GROUP-TAX-1",
        "is_exempt": False,
        "percentage": Decimal("5.00"),
    }


@pytest.mark.django_db
def test_effective_payment_schedule_returns_full_dict(prop: Property) -> None:
    gf = prop.group.finance
    gf.deposit_required = True
    gf.deposit_calculation_type = DepositCalcType.PERCENT
    gf.deposit_amount = Decimal("25.00")
    gf.interim_required = True
    gf.interim_calculation_type = DepositCalcType.PERCENT
    gf.interim_amount = Decimal("50.00")
    gf.days_interim_due_before_arrival = 90
    gf.days_balance_due_before_arrival = 30
    gf.save()

    PropertyFinance.objects.create(
        property=prop,
        deposit_amount=Decimal("40.00"),  # override
    )

    result = prop.finance.effective_payment_schedule()
    assert result == {
        "deposit_required": True,
        "deposit_calculation_type": DepositCalcType.PERCENT,
        "deposit_amount": Decimal("40.00"),
        "interim_required": True,
        "interim_calculation_type": DepositCalcType.PERCENT,
        "interim_amount": Decimal("50.00"),
        "days_interim_due_before_arrival": 90,
        "days_balance_due_before_arrival": 30,
    }


@pytest.mark.django_db
def test_effective_security_deposit_policy_returns_full_dict(prop: Property) -> None:
    gf = prop.group.finance
    gf.security_deposit_required = True
    gf.security_deposit_calculation_type = SecurityDepositCalcType.FIXED
    gf.security_deposit_amount = Decimal("500.00")
    gf.security_deposit_calculate_from = SecurityDepositCalcFrom.TOTAL_STAY
    gf.security_deposit_days_due_before_arrival = 14
    gf.security_deposit_days_refunded_after_departure = 7
    gf.security_deposit_payment_method = SecurityDepositPaymentMethod.CARD_HOLD
    gf.save()

    PropertyFinance.objects.create(
        property=prop,
        security_deposit_amount=Decimal("1000.00"),
        security_deposit_payment_method=SecurityDepositPaymentMethod.BANK_TRANSFER,
    )

    result = prop.finance.effective_security_deposit_policy()
    assert result == {
        "required": True,
        "calculation_type": SecurityDepositCalcType.FIXED,
        "amount": Decimal("1000.00"),
        "calculate_from": SecurityDepositCalcFrom.TOTAL_STAY,
        "days_due_before_arrival": 14,
        "days_refunded_after_departure": 7,
        "payment_method": SecurityDepositPaymentMethod.BANK_TRANSFER,
    }


@pytest.mark.django_db
def test_effective_cancellation_policy_returns_fields(prop: Property) -> None:
    gf = prop.group.finance
    gf.cancellation_fee_amount = Decimal("100.00")
    gf.cancellation_fee_percent = Decimal("25.00")
    gf.cancellation_window_days = 30
    gf.cancellation_notes = "group cancellation policy"
    gf.save()

    PropertyFinance.objects.create(
        property=prop,
        cancellation_fee_percent=Decimal("50.00"),  # override
    )

    result = prop.finance.effective_cancellation_policy()
    assert result == {
        "fee_amount": Decimal("100.00"),
        "fee_percent": Decimal("50.00"),
        "window_days": 30,
        "notes": "group cancellation policy",
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
