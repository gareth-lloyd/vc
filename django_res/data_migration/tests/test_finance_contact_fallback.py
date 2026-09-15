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
from data_migration.loaders.finance import (
    PropertyFinanceLoader,
    RateRowFinance,
    _finance_defaults,
)
from data_migration.tests.test_legacy_finance_defaults import CPD
from properties.enums import CommissionCalcType, DepositCalcType, SecurityDepositCalcType
from properties.models.contacts import PropertyContactAssignment
from properties.models.finance import PropertyFinance
from properties.models.geo import Country, Region
from properties.models.property import Property

pytestmark = pytest.mark.django_db


TEMPLATE: dict[str, Any] = {
    "Id": 1,
    "VillaId": None,
    "ContactId": 55,
    "ParentId": None,
    "CommissionTypeId": 20,
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
    "PaymentScheduleDepositTypeId": 10,
    "PaymentScheduleDepositAmount": Decimal("30"),
    "PaymentScheduleIsInterimRequired": False,
    "PaymentScheduleInterimTypeId": 0,
    "PaymentScheduleInterimAmount": None,
    "PaymentScheduleDaysInterimDueBeforeArrival": 0,
    "PaymentScheduleDaysBalanceDueBeforeArrival": 60,
    "SecurityDepositIsRequired": True,
    "SecurityDepositAmountTypeId": 20,
    "SecurityDepositAmount": Decimal("500"),
    "SecurityDepositDaysDueBeforeArrival": 14,
    "SecurityDepositDaysRefundedAfterDeparture": 7,
}


def test_finance_defaults_map_legacy_type_codes() -> None:
    # BUG-028: legacy codes are 10 = Percentage / 20 = Fixed; 0 = unset.
    d = _finance_defaults(TEMPLATE)
    assert d["commission_calculation_type"] == CommissionCalcType.FIXED
    assert d["deposit_calculation_type"] == DepositCalcType.PERCENT
    assert d["interim_calculation_type"] is None
    assert d["security_deposit_calculation_type"] == SecurityDepositCalcType.FIXED
    pct = _finance_defaults({**TEMPLATE, "SecurityDepositAmountTypeId": 10})
    assert pct["security_deposit_calculation_type"] == SecurityDepositCalcType.PERCENT


def _admin() -> User:
    return User.objects.create_user(
        email="a@a.com",
        password="x",
        role=StaffRole.ADMIN,
        is_staff=True,
    )


def _loader_with_templates(templates: dict[str, dict[str, Any]]) -> PropertyFinanceLoader:
    """A loader whose per-contact template and CPD caches are pre-seeded, so
    no test touches the legacy DB (`_by_contact` / `_cpd` read the caches)."""
    loader = PropertyFinanceLoader()
    loader._by_contact_cache = templates
    loader._cpd_cache = CPD
    loader._rate_finance_cache = {}
    return loader


@pytest.fixture
def villa_with_owner(db: None) -> tuple[Property, Person]:
    actor = _admin()
    country, _ = Country.objects.get_or_create(
        iso2="GR", defaults={"name": "Greece", "iso3": "GRC"}
    )
    region = Region.objects.create(country=country, name="Crete", slug="crete")
    prop = Property.objects.create(
        name="P",
        display_name="P",
        slug="p",
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
    # GAP-107: a fallback row has no legacy VillaFinance twin — the NULL
    # legacy_id is what lets `reconcile_legacy` leave it out of the count.
    assert finance.legacy_id is None


def test_process_row_skips_contact_default_template_rows(
    villa_with_owner: tuple[Property, Person],
) -> None:
    # `VillaFinance.VillaId` is `int NOT NULL`; template rows carry 0. They
    # must be skipped outright — never resolved via `legacy_id=""`.
    prop, _contact = villa_with_owner
    prop.legacy_id = ""
    prop.save(update_fields=["legacy_id"])
    loader = _loader_with_templates({})
    report = LoadReport(loader=loader.name)
    loader._process_row({"Id": 3, "VillaId": 0, "ContactId": 55, "ParentId": None}, report)
    assert report.skipped == 1
    assert not PropertyFinance.objects.filter(property=prop).exists()


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


def test_fallback_without_template_records_the_contact_and_cpd_values(
    villa_with_owner: tuple[Property, Person],
) -> None:
    # Parity: the old GroupFinance mirror carried the owner contact even when
    # no legacy template existed. BUG-028: legacy reads a villa with no
    # VillaFinance row as an all-zero model, so the <= 0 rule fills it from
    # the CPD — the row carries those values, not NULL policy columns.
    prop, contact = villa_with_owner
    loader = _loader_with_templates({"77": TEMPLATE})
    report = LoadReport(loader=loader.name)

    loader._apply_contact_defaults(report)

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.contact_id == contact.pk
    assert finance.commission_calculation_type == CommissionCalcType.PERCENT
    assert finance.commission_amount == Decimal("20.00")
    assert finance.security_deposit_calculation_type is not None
    assert finance.legacy_id is None
    assert report.created == 1


def test_fallback_villa_without_owner_gets_cpd_values_and_no_contact(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, _contact = villa_with_owner
    PropertyContactAssignment.objects.filter(property=prop).delete()
    loader = _loader_with_templates({"55": TEMPLATE})
    report = LoadReport(loader=loader.name)

    loader._apply_contact_defaults(report)

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.contact_id is None
    assert finance.commission_amount == Decimal("20.00")
    assert finance.deposit_required is False  # unflagged all-zero model: bools stay False
    assert not finance.bank_account_name
    assert report.created == 1


def test_fallback_villa_without_owner_takes_its_rate_row_majority(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, _contact = villa_with_owner
    PropertyContactAssignment.objects.filter(property=prop).delete()
    loader = _loader_with_templates({})
    loader._rate_finance_cache = {"900": _FIFTEEN_PERCENT}

    loader._apply_contact_defaults(LoadReport(loader=loader.name))

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.commission_amount == Decimal("15.00")
    assert finance.tax_percentage == Decimal("13")


def test_fallback_ignores_ended_owner_assignments(
    villa_with_owner: tuple[Property, Person],
) -> None:
    from datetime import date

    prop, _contact = villa_with_owner
    PropertyContactAssignment.objects.filter(property=prop).update(end_date=date(2020, 1, 1))
    loader = _loader_with_templates({"55": TEMPLATE})
    loader._apply_contact_defaults(LoadReport(loader=loader.name))
    # The only OWNER assignment has ended — a former owner's bank details
    # must never be stamped onto the villa (it still gets the CPD values).
    finance = PropertyFinance.objects.get(property=prop)
    assert finance.contact_id is None
    assert not finance.bank_account_name
    assert finance.commission_note != "Trip fee included"


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
    # BUG-028: NULL own commission is `<= 0`, so the CPD pair (20 %) wins
    # before the template is consulted — never CPD 20 with a template FIXED.
    assert finance.commission_calculation_type == CommissionCalcType.PERCENT
    assert finance.commission_amount == Decimal("20.00")
    assert finance.bank_iban == "GB29NWBK60161331926819"
    assert finance.contact_id == contact.pk
    # GAP-107: the per-villa pass stamps the legacy VillaFinance.Id.
    assert finance.legacy_id == "10"


def test_process_row_zero_commission_takes_cpd_not_template(
    villa_with_owner: tuple[Property, Person],
) -> None:
    # BUG-028 (legacy-exact fill order): an own 0 amount is `<= 0`, so the
    # global CPD amount (20) replaces it — the template's 12.50 never wins.
    prop, _contact = villa_with_owner
    loader = _loader_with_templates({"55": TEMPLATE})
    own_row: dict[str, Any] = {
        "Id": 10,
        "VillaId": 900,
        "ContactId": 55,
        "ParentId": None,
        "CommissionTypeId": 10,
        "CommissionAmount": Decimal("0"),
    }
    loader._process_row(own_row, LoadReport(loader=loader.name))

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.commission_calculation_type == CommissionCalcType.PERCENT
    assert finance.commission_amount == Decimal("20.00")


def test_process_row_flagged_commission_ignores_template_but_template_fills_bank(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, _contact = villa_with_owner
    loader = _loader_with_templates({"55": {**TEMPLATE, "CommissionAmount": Decimal("15")}})
    own_row: dict[str, Any] = {
        "Id": 10,
        "VillaId": 900,
        "ContactId": 55,
        "ParentId": None,
        "IsDefaultCommission": True,
        "CommissionTypeId": 20,
        "CommissionAmount": Decimal("99"),
        "BankAccAccountIBAN": None,
    }
    loader._process_row(own_row, LoadReport(loader=loader.name))

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.commission_calculation_type == CommissionCalcType.PERCENT
    assert finance.commission_amount == Decimal("20.00")
    assert finance.bank_iban == "GB29NWBK60161331926819"  # CPD has no bank


def test_process_row_applies_secdep_flag_and_unflagged_null_booleans_are_false(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, _contact = villa_with_owner
    loader = _loader_with_templates({})
    own_row: dict[str, Any] = {
        "Id": 10,
        "VillaId": 900,
        "ContactId": None,
        "ParentId": None,
        "CommissionTypeId": 10,
        "CommissionAmount": Decimal("18"),
        "IsDefaultSecDep": True,
        "SecurityDepositAmountTypeId": 20,
        "SecurityDepositAmount": Decimal("250"),
    }
    loader._process_row(own_row, LoadReport(loader=loader.name))

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.security_deposit_required is True
    assert finance.security_deposit_calculation_type == SecurityDepositCalcType.PERCENT
    assert finance.security_deposit_amount == Decimal("10.00")
    assert finance.security_deposit_days_due_before_arrival == 56
    assert finance.deposit_required is False  # NULL own boolean, unflagged
    assert finance.days_balance_due_before_arrival == 56  # NULL <= 0 -> CPD


def test_fallback_template_flags_are_stripped_and_zero_rule_applies(
    villa_with_owner: tuple[Property, Person],
) -> None:
    # A contact template row carries its own IsDefault* flags; they belong
    # to the template, not to the villa, so its own values stand — but the
    # `<= 0` rule still fills its zero fields from the CPD.
    prop, _contact = villa_with_owner
    template = {**TEMPLATE, "IsDefaultPaysched": True, "IsDefaultCommission": True}
    loader = _loader_with_templates({"55": template})
    loader._apply_contact_defaults(LoadReport(loader=loader.name))

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.commission_amount == Decimal("12.50")  # not CPD 20
    assert finance.days_balance_due_before_arrival == 60  # not CPD 56
    assert finance.interim_amount == Decimal("5.00")  # template NULL -> CPD
    assert finance.days_interim_due_before_arrival == 90  # template 0 -> CPD


def test_template_never_fills_a_type_whose_amount_the_cpd_resolved(
    villa_with_owner: tuple[Property, Person],
) -> None:
    # Flagged paysched with a CPD interim type of NULL: the interim type stays
    # unset rather than borrowing the template's type for the CPD amount.
    prop, _contact = villa_with_owner
    loader = _loader_with_templates({"55": {**TEMPLATE, "PaymentScheduleInterimTypeId": 20}})
    loader._cpd_cache = {**CPD, "InterimType": None}
    own_row: dict[str, Any] = {
        "Id": 10,
        "VillaId": 900,
        "ContactId": 55,
        "ParentId": None,
        "IsDefaultPaysched": True,
    }
    loader._process_row(own_row, LoadReport(loader=loader.name))

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.interim_amount == Decimal("5.00")
    assert finance.interim_calculation_type is None


@pytest.mark.django_db
def test_load_rows_fails_fast_when_cpd_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from data_migration.loaders import finance as finance_module

    calls = []

    def _missing() -> dict[str, Any]:
        calls.append(1)
        raise RuntimeError("VillaConfigPropertyDefault has no row")

    monkeypatch.setattr(finance_module, "fetch_config_property_default", _missing)
    loader = PropertyFinanceLoader()
    loader._by_contact_cache = {}
    with pytest.raises(RuntimeError):
        loader._load_rows([{"Id": 1, "VillaId": 900}], LoadReport(loader=loader.name))
    assert calls == [1]


_FIFTEEN_PERCENT = RateRowFinance(
    commission=(10, Decimal("15.00")),
    tax=(Decimal("13"), False),
    commission_mixed=False,
    tax_mixed=False,
)


def test_process_row_flagged_commission_uses_rate_row_majority_over_cpd(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, _contact = villa_with_owner
    loader = _loader_with_templates({})
    loader._rate_finance_cache = {"900": _FIFTEEN_PERCENT}
    own_row: dict[str, Any] = {
        "Id": 10,
        "VillaId": 900,
        "ContactId": None,
        "ParentId": None,
        "IsDefaultCommission": True,
        "CommissionTypeId": 20,
        "CommissionAmount": Decimal("0"),
        "TaxPercentage": None,
    }
    loader._process_row(own_row, LoadReport(loader=loader.name))

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.commission_calculation_type == CommissionCalcType.PERCENT
    assert finance.commission_amount == Decimal("15.00")
    assert finance.tax_percentage == Decimal("13")


def test_process_row_flagged_commission_without_rate_rows_uses_cpd(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, _contact = villa_with_owner
    loader = _loader_with_templates({})
    own_row: dict[str, Any] = {
        "Id": 10,
        "VillaId": 900,
        "ContactId": None,
        "ParentId": None,
        "IsDefaultCommission": True,
        "CommissionTypeId": 20,
        "CommissionAmount": Decimal("12"),
    }
    loader._process_row(own_row, LoadReport(loader=loader.name))
    assert PropertyFinance.objects.get(property=prop).commission_amount == Decimal("20.00")


def test_process_row_own_explicit_commission_loses_to_rate_row_majority(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, _contact = villa_with_owner
    loader = _loader_with_templates({})
    loader._rate_finance_cache = {"900": _FIFTEEN_PERCENT}
    own_row: dict[str, Any] = {
        "Id": 10,
        "VillaId": 900,
        "ContactId": None,
        "ParentId": None,
        "IsDefaultCommission": False,
        "CommissionTypeId": 20,
        "CommissionAmount": Decimal("150"),
        "TaxExempt": False,
        "TaxPercentage": Decimal("10"),
    }
    loader._process_row(own_row, LoadReport(loader=loader.name))

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.commission_calculation_type == CommissionCalcType.PERCENT
    assert finance.commission_amount == Decimal("15.00")
    assert finance.tax_percentage == Decimal("13")


def test_fallback_villa_gets_the_rate_row_majority(
    villa_with_owner: tuple[Property, Person],
) -> None:
    prop, _contact = villa_with_owner
    # The template's positive 12.50 FIXED / 20 % tax are not the villa's own
    # values, so the villa's rate-row majority beats them (review fix).
    loader = _loader_with_templates({"55": TEMPLATE})
    loader._rate_finance_cache = {"900": _FIFTEEN_PERCENT}
    loader._apply_contact_defaults(LoadReport(loader=loader.name))

    finance = PropertyFinance.objects.get(property=prop)
    assert finance.commission_calculation_type == CommissionCalcType.PERCENT
    assert finance.commission_amount == Decimal("15.00")
    assert finance.tax_percentage == Decimal("13")
    assert finance.bank_account_name == "Owner Ltd"  # template still fills the rest


def test_loader_defaults_reference_date_to_today() -> None:
    from datetime import date

    assert PropertyFinanceLoader().reference_date == date.today()
    assert PropertyFinanceLoader(reference_date=date(2025, 1, 1)).reference_date == date(2025, 1, 1)


def test_rate_row_query_uses_the_priced_predicate_and_reference_date() -> None:
    from datetime import date

    from data_migration.loaders.finance import rate_row_finance_query
    from data_migration.loaders.pricing import PRICED_ROW_PREDICATE

    query = rate_row_finance_query(date(2025, 4, 24))
    assert PRICED_ROW_PREDICATE in query
    assert "r.ToDate >= '2025-04-24'" in query
    assert "ISNULL(r.IsPOA, 0) = 0" in query
    assert "GROUP BY s.VillaId" in query
