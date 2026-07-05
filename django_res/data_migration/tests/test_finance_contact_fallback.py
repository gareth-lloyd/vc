"""PropertyFinanceLoader owner-contact fallback (GAP-070 unit 6, decision 7).

A villa with no `VillaFinance` row of its own inherits its primary-OWNER
contact's default template (the `VillaId IS NULL, ContactId NOT NULL,
ParentId NULL` rows) — written concretely into `PropertyFinance`, contact
included. Villas WITH their own row get NULL/"" fields merged from the same
template (pre-GAP-070 those resolved through GroupFinance + `effective()` at
read time; post-GAP-070 the resolution happens once, at load time).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from accounts.enums import ContactRole
from accounts.models import Person, User
from core.enums import StaffRole
from data_migration.base import LoadReport
from data_migration.loaders.finance import PropertyFinanceLoader
from properties.enums import CommissionCalcType
from properties.models.contacts import PropertyContactAssignment
from properties.models.finance import PropertyFinance
from properties.models.geo import Country, Region
from properties.models.property import Property, PropertyCategory

pytestmark = pytest.mark.django_db


TEMPLATE: dict[str, Any] = {
    "Id": 1,
    "VillaId": None,
    "ContactId": 55,
    "ParentId": None,
    "CommissionTypeId": 2,
    "CommissionAmount": Decimal("12.50"),
    "CommissionNote": "Trip fee included",
    "TaxNumber": "GB-123",
    "TaxExempt": False,
    "TaxPercentage": Decimal("20"),
    "BankAccAccountname": "Owner Ltd",
    "BankAccAccountnumber": "",
    "BankAccAccountSortCode": "",
    "BankAccAccountIBAN": "GB29NWBK60161331926819",
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
    "SecurityDepositDaysDueBeforeArrival": 14,
    "SecurityDepositDaysRefundedAfterDeparture": 7,
}


def _admin() -> User:
    return User.objects.create_user(
        email="a@a.com",
        password="x",
        role=StaffRole.ADMIN,
        is_staff=True,
    )


def _loader_with_templates(templates: dict[str, dict[str, Any]]) -> PropertyFinanceLoader:
    """A loader whose per-contact template cache is pre-seeded, so no test
    touches the legacy DB (`_by_contact` reads the cache when present)."""
    loader = PropertyFinanceLoader()
    loader._by_contact_cache = templates
    return loader


@pytest.fixture
def villa_with_owner(db: None) -> tuple[Property, Person]:
    actor = _admin()
    country, _ = Country.objects.get_or_create(
        iso2="GR", defaults={"name": "Greece", "iso3": "GRC"}
    )
    region = Region.objects.create(country=country, name="Crete", slug="crete")
    cat = PropertyCategory.objects.create(name="Villa", slug="villa")
    prop = Property.objects.create(
        name="P",
        display_name="P",
        slug="p",
        category=cat,
        region=region,
        legacy_id="900",
    )
    contact = Person.objects.create(
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
    return prop, contact


# ---------------------------------------------------------------------------
# Fallback pass — villas with NO row of their own
# ---------------------------------------------------------------------------
def test_fallback_applies_owner_template_to_financeless_villa(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, contact = villa_with_owner
    loader = _loader_with_templates({"55": TEMPLATE})
    report = LoadReport(loader=loader.name)

    loader._apply_contact_defaults(report)

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.contact_id == contact.pk
    assert finance.commission_amount == Decimal("12.50")
    assert finance.commission_note == "Trip fee included"
    assert finance.bank_account_name == "Owner Ltd"
    assert finance.deposit_required is True
    assert finance.security_deposit_amount == Decimal("500")
    assert report.created == 1


def test_fallback_never_touches_a_villa_with_its_own_row(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, _ = villa_with_owner
    PropertyFinance.objects.create(property=prop, commission_amount=Decimal("5"))
    loader = _loader_with_templates({"55": TEMPLATE})
    report = LoadReport(loader=loader.name)

    loader._apply_contact_defaults(report)

    prop.finance.refresh_from_db()
    assert prop.finance.commission_amount == Decimal("5")
    assert report.created == 0


def test_fallback_without_template_still_records_the_contact(
    villa_with_owner: tuple[Property, Person],
) -> None:
    # Parity: the old GroupFinance mirror carried the owner contact even when
    # no legacy template existed; the NULL policy columns read as the floor.
    prop, contact = villa_with_owner
    loader = _loader_with_templates({"77": TEMPLATE})
    report = LoadReport(loader=loader.name)

    loader._apply_contact_defaults(report)

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.contact_id == contact.pk
    assert finance.commission_amount is None
    assert report.created == 1


def test_fallback_skips_villa_without_owner_assignment(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, _contact = villa_with_owner
    PropertyContactAssignment.objects.filter(property=prop).delete()
    loader = _loader_with_templates({"55": TEMPLATE})
    loader._apply_contact_defaults(LoadReport(loader=loader.name))
    assert not PropertyFinance.objects.filter(property=prop).exists()


def test_fallback_ignores_ended_owner_assignments(
    villa_with_owner: tuple[Property, Person],
) -> None:
    from datetime import date

    prop, _contact = villa_with_owner
    PropertyContactAssignment.objects.filter(property=prop).update(end_date=date(2020, 1, 1))
    loader = _loader_with_templates({"55": TEMPLATE})
    loader._apply_contact_defaults(LoadReport(loader=loader.name))
    # The only OWNER assignment has ended — a former owner's bank details
    # must never be stamped onto the villa.
    assert not PropertyFinance.objects.filter(property=prop).exists()


def test_fallback_uses_non_primary_owner_when_no_primary(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, contact = villa_with_owner
    PropertyContactAssignment.objects.filter(property=prop).update(is_primary=False)
    loader = _loader_with_templates({"55": TEMPLATE})
    report = LoadReport(loader=loader.name)

    loader._apply_contact_defaults(report)

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.contact_id == contact.pk
    assert report.created == 1


def test_fallback_resolves_migrated_owner_past_a_primary_without_legacy_id(
    villa_with_owner: tuple[Property, Person],
) -> None:
    # A primary owner created in the NEW system (no legacy_id) can never
    # match a template; the migrated non-primary owner must resolve instead.
    prop, migrated = villa_with_owner
    PropertyContactAssignment.objects.filter(property=prop).update(is_primary=False)
    actor = User.objects.get(email="a@a.com")
    new_owner = Person.objects.create(
        first_name="N",
        last_name="EW",
        created_by=actor,
        updated_by=actor,
    )
    PropertyContactAssignment.objects.create(
        property=prop,
        contact=new_owner,
        role=ContactRole.OWNER,
        is_primary=True,
        created_by=actor,
        updated_by=actor,
    )
    loader = _loader_with_templates({"55": TEMPLATE})
    loader._apply_contact_defaults(LoadReport(loader=loader.name))

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.contact_id == migrated.pk


def test_fallback_excludes_villas_seen_in_the_row_pass(
    villa_with_owner: tuple[Property, Person],
) -> None:
    # A villa whose legacy VillaFinance row appeared in this load (even if
    # its write errored) must not be masked by a template row.
    prop, _contact = villa_with_owner
    loader = _loader_with_templates({"55": TEMPLATE})
    loader._apply_contact_defaults(
        LoadReport(loader=loader.name),
        exclude_legacy_ids={"900"},
    )
    assert not PropertyFinance.objects.filter(property=prop).exists()


def test_fallback_ignores_properties_without_legacy_id(
    villa_with_owner: tuple[Property, Person],
) -> None:
    # Non-migrated properties (created in the new system) are outside the
    # loader's universe — they get their rows via `snapshot_defaults`.
    prop, _contact = villa_with_owner
    new_prop = Property.objects.create(
        name="New",
        display_name="New",
        slug="new",
        category=prop.category,
        region=prop.region,
    )
    loader = _loader_with_templates({"55": TEMPLATE})
    loader._apply_contact_defaults(LoadReport(loader=loader.name))
    assert not PropertyFinance.objects.filter(property=new_prop).exists()


# ---------------------------------------------------------------------------
# Per-villa pass — NULL/"" fields on a villa's OWN row merge from the template
# ---------------------------------------------------------------------------
def test_process_row_merges_template_under_null_own_fields(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, contact = villa_with_owner
    loader = _loader_with_templates({"55": TEMPLATE})
    report = LoadReport(loader=loader.name)

    # The villa's own row carries only a tax number; commission and bank
    # are NULL/blank — pre-GAP-070 these resolved through the owner template.
    own_row: dict[str, Any] = {
        "Id": 10,
        "VillaId": 900,
        "ContactId": 55,
        "ParentId": None,
        "TaxNumber": "OWN-42",
        "CommissionTypeId": None,
        "CommissionAmount": None,
        "BankAccAccountIBAN": "",
    }
    loader._process_row(own_row, report)

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.tax_number == "OWN-42"  # own value wins
    assert finance.commission_calculation_type == CommissionCalcType.FIXED
    assert finance.commission_amount == Decimal("12.50")
    assert finance.bank_iban == "GB29NWBK60161331926819"
    assert finance.contact_id == contact.pk


def test_process_row_own_values_beat_the_template(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, _contact = villa_with_owner
    loader = _loader_with_templates({"55": TEMPLATE})
    own_row: dict[str, Any] = {
        "Id": 10,
        "VillaId": 900,
        "ContactId": 55,
        "ParentId": None,
        "CommissionTypeId": 1,
        "CommissionAmount": Decimal("0"),  # explicit 0 is an own value
    }
    loader._process_row(own_row, LoadReport(loader=loader.name))

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.commission_calculation_type == CommissionCalcType.PERCENT
    assert finance.commission_amount == Decimal("0")
