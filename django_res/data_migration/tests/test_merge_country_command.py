from __future__ import annotations

import pytest
from django.core.management import call_command

from properties.models import Country, Region

pytestmark = pytest.mark.django_db


@pytest.fixture
def england() -> Country:
    source = Country.objects.create(name="England", iso2="UK", iso3="UKX", legacy_id="24")
    Region.objects.create(country=source, name="Cornwall", slug="cornwall")
    Country.objects.get_or_create(iso2="GB", defaults={"name": "United Kingdom", "iso3": "GBR"})
    return source


def test_dry_run_reports_and_rolls_back_without_failing(england: Country) -> None:
    # BUG-029 §4: a successful preview must not exit 1 — scripts treat that as failure.
    call_command("merge_country", from_legacy="24", to_iso2="GB", dry_run=True)

    assert Country.objects.filter(pk=england.pk).exists()
    assert Region.objects.get(slug="cornwall").country_id == england.pk


def test_merge_rewrites_references_and_deletes_source(england: Country) -> None:
    call_command("merge_country", from_legacy="24", to_iso2="GB")

    assert not Country.objects.filter(pk=england.pk).exists()
    assert Region.objects.get(slug="cornwall").country.iso2 == "GB"
