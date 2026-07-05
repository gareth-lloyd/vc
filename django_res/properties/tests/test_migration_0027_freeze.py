"""Freeze guard for properties migration 0027 (GAP-070 unit 3).

Before the group tables are dropped, 0027 resolves the old `effective()`
inheritance one final time and writes the result as concrete values on
`PropertySettings`/`PropertyFinance` — creating missing rows outright (legacy
properties without a VillaFinance row have no PropertyFinance row at all).
Resolution rule (the old `effective()` contract): own value wins unless it is
NULL or "", in which case the group row's value is frozen in; a NULL group
value stays NULL (decision 2 — no backfill-to-global).

Driven through `MigrationExecutor` against the historical state so the guard
stays valid after the later migration drops `PropertyGroup`/`GroupSettings`/
`GroupFinance`.
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from typing import Any

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import ProjectState

# Pin every app the seed touches (the 0011-test pattern): without the accounts
# pin the historical Person model freezes at the dependency-closure state while
# the live table sits at the accounts leaf — a future NOT NULL column on Person
# would make _seed's create() fail on an unrelated accounts change.
_BEFORE = [
    ("properties", "0026_propertydefaults"),
    ("accounts", "0016_user_tfa_last_verified_step"),
]
_AFTER = [("properties", "0027_freeze_group_inheritance")]


def _migrate(targets: list[tuple[str, str]]) -> ProjectState:
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets)


def _seed(state: ProjectState) -> dict[str, int]:
    apps = state.apps
    Country = apps.get_model("properties", "Country")
    Region = apps.get_model("properties", "Region")
    PropertyCategory = apps.get_model("properties", "PropertyCategory")
    PropertyGroup = apps.get_model("properties", "PropertyGroup")
    GroupSettings = apps.get_model("properties", "GroupSettings")
    GroupFinance = apps.get_model("properties", "GroupFinance")
    Property = apps.get_model("properties", "Property")
    PropertySettings = apps.get_model("properties", "PropertySettings")
    PropertyFinance = apps.get_model("properties", "PropertyFinance")
    Currency = apps.get_model("pricing", "Currency")
    Person = apps.get_model("accounts", "Person")

    country = Country.objects.get(iso2="GB")  # seeded by properties/0009
    region, _ = Region.objects.get_or_create(country=country, name="Cornwall", slug="cornwall")
    cat, _ = PropertyCategory.objects.get_or_create(name="Villa", slug="villa")
    eur, _ = Currency.objects.get_or_create(code="EUR", defaults={"name": "Euro", "symbol": "€"})
    owner = Person.objects.create(first_name="Group", last_name="Owner")

    # Historical models fire no signals — group rows are created explicitly.
    group = PropertyGroup.objects.create(name="Freeze G")
    GroupSettings.objects.create(
        group=group,
        currency=eur,
        check_in_time=time(15, 0),
        changeover_day="sat",
        min_nights_rental=7,
        min_nights_rental_note="Min stay 7",
    )
    GroupFinance.objects.create(
        group=group,
        contact=owner,
        commission_amount=Decimal("20"),
        tax_number="TX123",
        bank_account_name="Group Bank",
        tax_is_exempt=True,
    )

    def make_property(slug: str, grp: Any) -> Any:
        return Property.objects.create(
            name=slug, display_name=slug, slug=slug, category=cat, group=grp, region=region
        )

    # A: has rows — own values win; NULL and "" inherit.
    prop_a = make_property("freeze-a", group)
    PropertySettings.objects.create(
        property=prop_a,
        changeover_day="wed",  # own value — kept
        currency=None,  # NULL — inherits EUR
        min_nights_rental_note="",  # "" — inherits the group note
        hold_duration_hours=None,  # NULL — inherits group default 48
    )
    PropertyFinance.objects.create(
        property=prop_a,
        commission_amount=Decimal("12"),  # own value — kept
        deposit_amount=None,  # NULL — inherits group default 30
        bank_account_name="",  # "" — inherits "Group Bank"
        # Falsy own values are OWN VALUES, not "inherit" — the old effective()
        # only treated NULL/"" as inherit. Must survive the freeze unchanged.
        tax_is_exempt=False,  # group has True — False must be kept
        interim_amount=Decimal("0"),  # group default 0 anyway, but explicit falsy
        cancellation_window_days=0,  # falsy int — kept
    )

    # B: NO settings/finance rows at all — both get created from the group.
    prop_b = make_property("freeze-b", group)

    # C: group whose own currency is NULL — stays NULL after the freeze.
    group_null = PropertyGroup.objects.create(name="Freeze G null")
    GroupSettings.objects.create(group=group_null, currency=None)
    GroupFinance.objects.create(group=group_null)
    prop_c = make_property("freeze-c", group_null)
    PropertySettings.objects.create(property=prop_c, currency=None)

    # D: group with NEITHER settings nor finance row (bulk-created groups
    # bypass the auto-create signals) — nothing to resolve; property values
    # survive untouched and the migration must not crash.
    group_bare = PropertyGroup.objects.create(name="Freeze G bare")
    prop_d = make_property("freeze-d", group_bare)
    PropertySettings.objects.create(property=prop_d, changeover_day="fri")

    return {"a": prop_a.pk, "b": prop_b.pk, "c": prop_c.pk, "d": prop_d.pk}


@pytest.mark.django_db(transaction=True)
def test_migration_0027_freezes_effective_values() -> None:
    before = _migrate(_BEFORE)
    try:
        pks = _seed(before)

        after = _migrate(_AFTER)
        PropertySettings = after.apps.get_model("properties", "PropertySettings")
        PropertyFinance = after.apps.get_model("properties", "PropertyFinance")
        Currency = after.apps.get_model("pricing", "Currency")
        Person = after.apps.get_model("accounts", "Person")
        eur = Currency.objects.get(code="EUR")
        owner = Person.objects.get(first_name="Group", last_name="Owner")

        # A — own values kept; NULL/"" resolved to the group's values.
        settings_a = PropertySettings.objects.get(property_id=pks["a"])
        assert settings_a.changeover_day == "wed"
        assert settings_a.currency_id == eur.pk
        assert settings_a.min_nights_rental_note == "Min stay 7"
        assert settings_a.hold_duration_hours == 48
        assert settings_a.check_in_time == time(15, 0)
        assert settings_a.min_nights_rental == 7
        finance_a = PropertyFinance.objects.get(property_id=pks["a"])
        assert finance_a.commission_amount == Decimal("12")
        assert finance_a.deposit_amount == Decimal("30")
        assert finance_a.bank_account_name == "Group Bank"
        assert finance_a.tax_number == "TX123"
        assert finance_a.contact_id == owner.pk
        # Falsy own values survived (a truthiness-based freeze would clobber them).
        assert finance_a.tax_is_exempt is False
        assert finance_a.interim_amount == Decimal("0")
        assert finance_a.cancellation_window_days == 0

        # B — rows created wholesale from the group floor.
        settings_b = PropertySettings.objects.get(property_id=pks["b"])
        assert settings_b.currency_id == eur.pk
        assert settings_b.min_nights_rental == 7
        assert settings_b.changeover_day == "sat"
        finance_b = PropertyFinance.objects.get(property_id=pks["b"])
        assert finance_b.commission_amount == Decimal("20")
        assert finance_b.contact_id == owner.pk
        assert finance_b.deposit_required is True

        # C — a NULL group value stays NULL (no backfill-to-global).
        settings_c = PropertySettings.objects.get(property_id=pks["c"])
        assert settings_c.currency_id is None
        assert settings_c.check_in_time is None

        # D — group without settings/finance rows: values survive untouched.
        settings_d = PropertySettings.objects.get(property_id=pks["d"])
        assert settings_d.changeover_day == "fri"
        assert settings_d.currency_id is None
        finance_d = PropertyFinance.objects.get(property_id=pks["d"])
        assert finance_d.commission_amount is None
    finally:
        call_command("migrate", verbosity=0)
