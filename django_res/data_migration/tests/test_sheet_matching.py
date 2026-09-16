"""GAP-089: shared matching helpers for the spreadsheet importers."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from accounts.enums import PersonKind, PersonStatus, PersonTag
from accounts.models import Person, PersonEmail
from data_migration.sheets.matching import (
    PropertyMatcher,
    append_note_line,
    channels_writable,
    fill_blanks,
    find_or_create_person,
    html_to_text,
    map_tags,
    match_person_by_email,
    match_person_by_name,
    normalise_name,
    parse_sheet_date,
    person_legacy_id,
    resolve_country,
    resolve_region,
    split_tags,
)
from properties.enums import PropertyStatus
from properties.models import Country, Property, Region

pytestmark = pytest.mark.django_db


# --- pure helpers -----------------------------------------------------------


def test_normalise_name_casefolds_and_strips_punctuation() -> None:
    assert normalise_name("  O'Brien-Smith ") == "obrien smith"
    assert normalise_name("Villa   Yeraki") == "villa yeraki"
    assert normalise_name(None) == ""


def test_split_tags_accepts_semicolons_and_commas() -> None:
    assert split_tags("VIP; PA, Owner") == ["VIP", "PA", "Owner"]
    assert split_tags(None) == []


def test_map_tags_maps_known_and_reports_unknown() -> None:
    tags, unknown = map_tags("VIP?; NC, Owner; LC; HNW; NWC; Trade; PA")

    assert tags == [
        PersonTag.VIP,
        PersonTag.NICKS_FRIEND,
        PersonTag.OWNER,
        PersonTag.HNW,
        PersonTag.NICKS_NETWORK,
        PersonTag.TRADE,
        PersonTag.PA,
    ]
    assert unknown == ["LC"]


def test_parse_sheet_date_handles_iso_strings_dates_and_junk() -> None:
    assert parse_sheet_date("2019-06-01") == date(2019, 6, 1)
    assert parse_sheet_date("2019-06-01 00:00:00") == date(2019, 6, 1)
    assert parse_sheet_date(datetime(2019, 6, 1, 9)) == date(2019, 6, 1)
    assert parse_sheet_date(date(2019, 6, 1)) == date(2019, 6, 1)
    assert parse_sheet_date("01/06/2019") == date(2019, 6, 1)
    assert parse_sheet_date("soon") is None
    assert parse_sheet_date(None) is None


def test_html_to_text_flattens_breaks_and_entities() -> None:
    assert html_to_text("Hi<br />there<br>&amp; <b>bye</b>") == "Hi\nthere\n& bye"
    assert html_to_text(None) == ""


# --- villa matching ----------------------------------------------------------


def _property(name: str, display_name: str | None = None, **fields: object) -> Property:
    country, _ = Country.objects.get_or_create(
        iso2="GR", defaults={"name": "Greece", "iso3": "GRC"}
    )
    region, _ = Region.objects.get_or_create(country=country, name="Corfu", slug="corfu")
    return Property.objects.create(
        name=name,
        display_name=display_name or name,
        slug=f"{normalise_name(name).replace(' ', '-')}-{Property.objects.count()}",
        region=region,
        **fields,
    )


def test_property_matcher_exact_prefix_and_ambiguous() -> None:
    yeraki = _property("Villa Yeraki")
    ilios = _property("Ilios", display_name="Ilios House")
    _property("Twin")
    _property("Villa Twin")
    matcher = PropertyMatcher()

    assert matcher.match("Yeraki") == yeraki
    assert matcher.match("villa  yeraki") == yeraki
    assert matcher.match("Villa Ilios") == ilios
    assert matcher.match("Ilios House") == ilios
    # Two distinct properties collapse to the same stripped key → ambiguous.
    assert matcher.match("Twin") is None
    assert matcher.match("Yeraki / Ilios") is None
    assert matcher.match("") is None


# --- geo ------------------------------------------------------------------


def _country(iso2: str, iso3: str, name: str) -> Country:
    country, _ = Country.objects.get_or_create(iso2=iso2, defaults={"iso3": iso3, "name": name})
    return country


def test_resolve_country_uses_alias_map_then_iso_names() -> None:
    # Countries are seeded reference data (conftest) — look up, don't create.
    gb = _country("GB", "GBR", "United Kingdom")
    us = _country("US", "USA", "United States")
    fr = _country("FR", "FRA", "France")
    Country.objects.filter(iso2="XK").delete()

    assert resolve_country("UK") == gb
    assert resolve_country("united kingdom") == gb
    assert resolve_country("USA") == us
    assert resolve_country("France") == fr
    assert resolve_country("Channel Islands") is None
    assert resolve_country("Kosovo") is None  # ISO name known, no Country row
    assert resolve_country("Frrance") is None
    assert resolve_country(None) is None


def test_resolve_region_requires_exactly_one_hit() -> None:
    gr = _country("GR", "GRC", "Greece")
    it = _country("IT", "ITA", "Italy")
    corfu = Region.objects.create(country=gr, name="Corfu", slug="corfu")
    Region.objects.create(country=gr, name="Twin", slug="twin-gr")
    Region.objects.create(country=it, name="Twin", slug="twin-it")

    assert resolve_region("Greece", "corfu") == corfu
    assert resolve_region(None, "Corfu") == corfu
    assert resolve_region(None, "Twin") is None
    assert resolve_region("Italy", "Corfu") is None
    assert resolve_region("Greece", "Corfu / Paxos") is None
    assert resolve_region("Greece", None) is None


# --- persons ---------------------------------------------------------------


def _person(first: str, last: str, email: str | None = None, **kwargs: object) -> Person:
    person = Person.objects.create(first_name=first, last_name=last, **kwargs)
    if email:
        PersonEmail.objects.create(contact=person, email=email, is_primary=True)
    return person


def test_find_person_by_email_and_last_name() -> None:
    ada = _person("Ada", "Lovelace", "ada@example.com")

    match = find_or_create_person(
        email="ADA@example.com", first_name="Ada", last_name="lovelace", legacy_id="sheet-person-1"
    )

    assert match.person == ada
    assert match.created is False
    assert match.ambiguous is False


def test_same_email_different_last_name_creates_second_person() -> None:
    _person("Orlando", "Fraser", "fraser@example.com")

    match = find_or_create_person(
        email="fraser@example.com",
        first_name="Clemmie",
        last_name="Smith",
        legacy_id="sheet-person-2",
    )

    assert match.created is True
    assert match.person.legacy_id == "sheet-person-2"
    assert match.person.kind == PersonKind.CUSTOMER
    assert list(match.person.emails.values_list("email", flat=True)) == ["fraser@example.com"]
    assert Person.objects.filter(emails__email="fraser@example.com").count() == 2


def test_blank_first_name_still_matches_on_email_and_last_name() -> None:
    ada = _person("Ada", "Lovelace", "ada@example.com")

    match = find_or_create_person(
        email="ada@example.com", first_name="", last_name="Lovelace", legacy_id="sheet-person-3"
    )

    assert match.person == ada


def test_no_email_matches_exactly_one_active_customer_by_name() -> None:
    ada = _person("Ada", "Lovelace", kind=PersonKind.CUSTOMER)
    _person("Ada", "Lovelace", kind=PersonKind.CONTACT)  # non-customer namesake loses
    _person("Ada", "Lovelace", status=PersonStatus.INACTIVE, kind=PersonKind.CUSTOMER)

    match = find_or_create_person(
        email=None, first_name="ada", last_name="LOVELACE", legacy_id="sheet-person-4"
    )

    assert match.person == ada
    assert match.created is False


def test_no_email_ambiguous_name_creates_and_flags() -> None:
    _person("Ada", "Lovelace", kind=PersonKind.CUSTOMER)
    _person("Ada", "Lovelace", kind=PersonKind.CUSTOMER)

    match = find_or_create_person(
        email=None, first_name="Ada", last_name="Lovelace", legacy_id="sheet-person-5"
    )

    assert match.created is True
    assert match.ambiguous is True
    assert match.person.emails.count() == 0


def test_rerun_finds_by_legacy_id_and_only_fills_blanks() -> None:
    first = find_or_create_person(
        email="new@example.com",
        first_name="New",
        last_name="Person",
        legacy_id="sheet-person-6",
        defaults={"title": "Mr", "town": "Bath"},
    )
    assert first.created is True
    assert first.person.title == "Mr"
    first.person.town = "Bristol"  # operator edit
    first.person.save(update_fields=["town"])

    again = find_or_create_person(
        email="new@example.com",
        first_name="New",
        last_name="Person",
        legacy_id="sheet-person-6",
        defaults={"title": "Dr", "town": "Bath", "post_code": "BA1"},
    )

    assert again.created is False
    assert again.person == first.person
    again.person.refresh_from_db()
    assert again.person.title == "Mr"  # not overwritten
    assert again.person.town == "Bristol"  # operator edit survives
    assert again.person.post_code == "BA1"  # blank → filled


def test_requires_a_name_or_email() -> None:
    with pytest.raises(ValueError, match="name or email"):
        find_or_create_person(email=None, first_name="", last_name="", legacy_id="x")


def test_append_note_line_is_idempotent() -> None:
    person = _person("Ada", "Lovelace")

    assert append_note_line(person, "Agent/advisor: Bob") is True
    assert append_note_line(person, "Agent/advisor: Bob") is False
    assert append_note_line(person, "Sheet tags: LC") is True
    assert append_note_line(person, "") is False

    person.refresh_from_db()
    assert person.notes == "Agent/advisor: Bob\nSheet tags: LC"


# --- review hardening (Unit 2 review, 2026-09-02) ----------------------------


def test_resolve_region_scopes_country_through_the_alias_map() -> None:
    gb, _ = Country.objects.get_or_create(iso2="GB", defaults={"name": "United Kingdom"})
    gr, _ = Country.objects.get_or_create(iso2="GR", defaults={"name": "Greece"})
    cornwall = Region.objects.create(country=gb, name="Cornwall", slug="cornwall")
    Region.objects.create(country=gr, name="Cornwall", slug="cornwall-gr")  # same name

    assert resolve_region("UK", "Cornwall") == cornwall
    assert resolve_region("England", "cornwall") == cornwall
    assert resolve_region("Atlantis", "Cornwall") is None  # unknown country → no guess


def test_email_only_row_matches_the_existing_person_on_that_address() -> None:
    john = _person("John", "Smith", "john@example.com")

    match = find_or_create_person(
        email="john@example.com",
        first_name="",
        last_name="",
        legacy_id=person_legacy_id("john@example.com", "", ""),
    )

    assert match.person == john
    assert match.created is False
    assert PersonEmail.objects.filter(email="john@example.com").count() == 1


def test_rerun_leaves_an_anonymised_sheet_person_alone() -> None:
    legacy_id = person_legacy_id("ada@example.com", "Ada", "Lovelace")
    first = find_or_create_person(
        email="ada@example.com",
        first_name="Ada",
        last_name="Lovelace",
        legacy_id=legacy_id,
        defaults={"town": "Bath"},
    )
    first.person.anonymize()

    again = find_or_create_person(
        email="ada@example.com",
        first_name="Ada",
        last_name="Lovelace",
        legacy_id=legacy_id,
        defaults={"town": "Bath"},
    )

    assert again.inactive is True
    assert again.created is False
    again.person.refresh_from_db()
    assert again.person.town == ""
    assert again.person.status == PersonStatus.ANONYMIZED
    assert Person.objects.count() == 1


def test_fill_blanks_treats_an_empty_list_as_blank() -> None:
    person = _person("Ada", "Lovelace", kind=PersonKind.CUSTOMER)
    assert person.tags == []

    assert fill_blanks(person, {"tags": [PersonTag.VIP], "town": ""}) == ["tags"]
    assert person.tags == [PersonTag.VIP]
    assert fill_blanks(person, {"tags": [PersonTag.PA]}) == []


def test_deactivated_person_on_the_same_email_is_reported_inactive_not_reminted() -> None:
    # A res-DB person the importer matched on run 1 never got a sheet key; if
    # staff deactivate them, run 2 must not mint a fresh copy from the sheet.
    _person("Ada", "Lovelace", "ada@example.com", status=PersonStatus.INACTIVE)

    match = find_or_create_person(
        email="ada@example.com",
        first_name="Ada",
        last_name="Lovelace",
        legacy_id=person_legacy_id("ada@example.com", "Ada", "Lovelace"),
    )

    assert match.inactive is True
    assert Person.objects.count() == 1


def test_namesakes_that_are_not_customers_are_flagged_ambiguous() -> None:
    _person("John", "Smith", kind=PersonKind.CONTACT)
    _person("John", "Smith", kind=PersonKind.CONTACT)

    assert match_person_by_name("John", "Smith") == (None, True)
    match = find_or_create_person(
        email=None, first_name="John", last_name="Smith", legacy_id="sheet-person-x"
    )
    assert match.created is True and match.ambiguous is True


def test_parse_sheet_date_ignores_a_time_suffix() -> None:
    assert parse_sheet_date("1/6/2019 00:00") == date(2019, 6, 1)
    assert parse_sheet_date("2019-06-01T09:15:00") == date(2019, 6, 1)
    assert parse_sheet_date("31/12/2020") == date(2020, 12, 31)


# --- BUG-030 §18: deterministic CUSTOMER-first e-mail match ---


def test_match_person_by_email_prefers_the_customer_over_a_contact() -> None:
    _person("Ada", "Lovelace", "ada@example.com", kind=PersonKind.CONTACT)
    customer = _person("Ada", "Lovelace", "ada@example.com", kind=PersonKind.CUSTOMER)

    assert match_person_by_email("ADA@example.com ", active_only=True) == customer


def test_match_person_by_email_ties_break_on_pk() -> None:
    first = _person("Ada", "Lovelace", "ada@example.com", kind=PersonKind.CUSTOMER)
    _person("Ada", "Lovelace", "ada@example.com", kind=PersonKind.CUSTOMER)

    assert match_person_by_email("ada@example.com", active_only=True) == first


def test_match_person_by_email_active_only_ignores_inactive_people() -> None:
    _person("Ada", "Lovelace", "ada@example.com", status=PersonStatus.INACTIVE)

    assert match_person_by_email("ada@example.com", active_only=True) is None
    assert match_person_by_email("ada@example.com", active_only=False) is not None


def test_match_person_by_email_any_status_still_puts_active_first() -> None:
    _person(
        "Ada", "Lovelace", "ada@example.com", status=PersonStatus.INACTIVE, kind=PersonKind.CUSTOMER
    )
    active = _person("Ada", "Lovelace", "ada@example.com", kind=PersonKind.CONTACT)

    assert match_person_by_email("ada@example.com", active_only=False) == active


def test_match_person_by_email_skips_a_namesake_disagreement() -> None:
    _person("Orlando", "Fraser", "fraser@example.com", kind=PersonKind.CUSTOMER)
    jane = _person("Jane", "Fraser", "fraser@example.com", kind=PersonKind.CONTACT)

    assert (
        match_person_by_email(
            "fraser@example.com", first_name="Jane", last_name="Fraser", active_only=True
        )
        == jane
    )
    assert match_person_by_email("fraser@example.com", last_name="Smith", active_only=True) is None


def test_match_person_by_email_matches_a_non_primary_address() -> None:
    person = _person("Ada", "Lovelace", "ada@example.com")
    PersonEmail.objects.create(contact=person, email="ada@work.example", is_primary=False)

    assert match_person_by_email("ada@work.example", active_only=True) == person


def test_match_person_by_email_blank_or_invalid_address_is_none() -> None:
    _person("Ada", "Lovelace", "ada@example.com")
    assert match_person_by_email("", active_only=False) is None
    assert match_person_by_email("not-an-email", active_only=False) is None


def test_find_or_create_person_uses_the_customer_first_match() -> None:
    _person("Ada", "Lovelace", "ada@example.com", kind=PersonKind.CONTACT)
    customer = _person("Ada", "Lovelace", "ada@example.com", kind=PersonKind.CUSTOMER)

    match = find_or_create_person(
        email="ada@example.com", first_name="Ada", last_name="Lovelace", legacy_id="sheet-person-9"
    )

    assert match.person == customer


# --- BUG-030 §33/§35 ---


def test_property_matcher_prefers_the_single_live_villa_over_archived_duplicates() -> None:
    live = _property("Villa Yeraki", status=PropertyStatus.ACTIVE)
    _property("Villa Yeraki", status=PropertyStatus.ARCHIVED)
    _property("Yeraki", status=PropertyStatus.ARCHIVED)
    draft = _property("Villa Olea", status=PropertyStatus.DRAFT)
    _property("Villa Olea", status=PropertyStatus.ARCHIVED)

    matcher = PropertyMatcher()

    assert matcher.match("Villa Yeraki") == live
    assert matcher.match("yeraki") == live
    assert matcher.match("Olea") == draft  # DRAFT is not archived


def test_property_matcher_falls_back_to_an_archived_only_name() -> None:
    old = _property("Villa Kalami", status=PropertyStatus.ARCHIVED)
    _property("Villa Yeraki", status=PropertyStatus.ACTIVE)

    assert PropertyMatcher().match("Kalami") == old


def test_property_matcher_two_live_namesakes_stay_ambiguous() -> None:
    _property("Villa Yeraki", status=PropertyStatus.ACTIVE)
    _property("Yeraki", status=PropertyStatus.DRAFT)
    _property("Villa Yeraki", status=PropertyStatus.ARCHIVED)

    assert PropertyMatcher().match("Yeraki") is None


def test_match_person_by_name_never_links_a_single_non_customer() -> None:
    _person("John", "Smith", kind=PersonKind.CONTACT)

    assert match_person_by_name("John", "Smith") == (None, True)


def test_match_person_by_name_links_a_single_customer_beside_contacts() -> None:
    customer = _person("John", "Smith", kind=PersonKind.CUSTOMER)
    _person("John", "Smith", kind=PersonKind.CONTACT)

    assert match_person_by_name("John", "Smith") == (customer, False)


def test_match_person_by_name_no_namesake_is_not_ambiguous() -> None:
    assert match_person_by_name("Nobody", "Here") == (None, False)


def test_property_matcher_exact_name_beats_a_live_prefix_strip() -> None:
    archived = _property("Villa Rosa", status=PropertyStatus.ARCHIVED)
    _property("Rosa", status=PropertyStatus.ACTIVE)

    assert PropertyMatcher().match("Villa Rosa") == archived


def test_active_owner_namesake_does_not_hide_a_deactivated_customer() -> None:
    _person("John", "Smith", kind=PersonKind.CONTACT)
    customer = _person("John", "Smith", kind=PersonKind.CUSTOMER, status=PersonStatus.INACTIVE)

    match = find_or_create_person(
        email=None, first_name="John", last_name="Smith", legacy_id="sheet-person-y"
    )

    assert match.inactive is True
    assert match.person == customer
    assert Person.objects.count() == 2


@pytest.mark.parametrize(
    ("legacy_id", "writable"),
    [(None, True), ("sheet-person-abc", True), ("client-12", True), ("4711", False)],
)
def test_channels_writable_only_for_sheet_client_and_hand_made_people(
    legacy_id: str | None, writable: bool
) -> None:
    assert channels_writable(legacy_id) is writable
