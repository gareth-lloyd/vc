from __future__ import annotations

from decimal import Decimal

import pytest

from accounts.enums import ContactRole
from accounts.models import Contact, User
from core.enums import StaffRole
from data_migration.base import LoadReport
from data_migration.loaders.finance import GroupFinanceLoader
from properties.models.contacts import PropertyContactAssignment
from properties.models.finance import GroupFinance
from properties.models.geo import Country, Region
from properties.models.property import Property, PropertyCategory, PropertyGroup


def _admin() -> User:
    return User.objects.create_user(
        email="a@a.com",
        password="x",
        role=StaffRole.ADMIN,
        is_staff=True,
    )


@pytest.fixture
def group_with_owner(db: None) -> tuple[PropertyGroup, Contact]:
    actor = _admin()
    country = Country.objects.get(iso2="GR")
    region = Region.objects.create(country=country, name="Crete", slug="crete")
    cat = PropertyCategory.objects.create(name="Villa", slug="villa")
    group = PropertyGroup.objects.create(name="G", legacy_id="10")
    prop = Property.objects.create(
        name="P",
        display_name="P",
        slug="p",
        category=cat,
        group=group,
        region=region,
    )
    contact = Contact.objects.create(
        first_name="O",
        last_name="W",
        legacy_id="55",
        created_by=actor,
        updated_by=actor,
    )
    PropertyContactAssignment.objects.create(
        property=prop,
        contact=contact,
        role=ContactRole.OWNER,
        is_primary=True,
        created_by=actor,
        updated_by=actor,
    )
    return group, contact


@pytest.mark.django_db
def test_sync_one_with_no_legacy_template_falls_back_to_defaults(
    group_with_owner: tuple[PropertyGroup, Contact],
) -> None:
    group, contact = group_with_owner
    loader = GroupFinanceLoader()
    report = LoadReport(loader=loader.name)
    # Empty template dict — no legacy row matches this contact.
    loader._sync_group(group, {}, report)
    gf = GroupFinance.objects.get(group=group)
    assert gf.contact_id == contact.pk
    # Model schema defaults apply (commission_amount=0).
    assert gf.commission_amount == Decimal("0")
    assert report.created + report.updated == 1


@pytest.mark.django_db
def test_sync_one_copies_template_when_contact_matches(
    group_with_owner: tuple[PropertyGroup, Contact],
) -> None:
    group, contact = group_with_owner
    loader = GroupFinanceLoader()
    report = LoadReport(loader=loader.name)
    template = {
        "Id": 1,
        "CommissionTypeId": 2,
        "CommissionAmount": Decimal("12.50"),
        "CommissionNote": "Trip fee included",
        "TaxNumber": "GB-123",
        "TaxExempt": False,
        "TaxPercentage": Decimal("20"),
        "BankAccAccountname": "Owner Ltd",
        "BankAccAccountnumber": "",
        "BankAccAccountSortCode": "",
        "BankAccAccountIBAN": "",
        "BankAccAccountBIC": "",
        "BankAccAddres1": "",
        "BankAccAddres2": "",
        "BankAccPostCode": "",
        "BankAccTown": "",
        "PaymentScheduleIsDepositRequired": True,
        "PaymentScheduleDepositTypeId": 1,
        "PaymentScheduleDepositAmount": Decimal("30"),
        "PaymentScheduleIsInterimRequired": False,
        "PaymentScheduleInterimTypeId": 0,
        "PaymentScheduleInterimAmount": None,
        "PaymentScheduleDaysInterimDueBeforeArrival": 0,
        "PaymentScheduleDaysBalanceDueBeforeArrival": 60,
        "SecurityDepositIsRequired": True,
        "SecurityDepositAmountTypeId": 2,
        "SecurityDepositAmount": Decimal("500"),
        "SecurityDepositCalculateFromId": 3,
        "SecurityDepositDaysDueBeforeArrival": 14,
        "SecurityDepositDaysRefundedAfterDeparture": 7,
    }
    assert contact.legacy_id is not None
    loader._sync_group(group, {contact.legacy_id: template}, report)
    gf = GroupFinance.objects.get(group=group)
    assert gf.commission_amount == Decimal("12.50")
    assert gf.commission_note == "Trip fee included"
    assert gf.bank_account_name == "Owner Ltd"
    assert gf.deposit_required is True
    assert gf.security_deposit_amount == Decimal("500")


@pytest.mark.django_db
def test_sync_one_skips_template_when_no_owner_assignment(db: None) -> None:
    group = PropertyGroup.objects.create(name="No owner", legacy_id="99")
    loader = GroupFinanceLoader()
    report = LoadReport(loader=loader.name)
    loader._sync_group(group, {"55": {"CommissionAmount": Decimal("10")}}, report)
    gf = GroupFinance.objects.get(group=group)
    assert gf.contact_id is None
    assert gf.commission_amount == Decimal("0")
