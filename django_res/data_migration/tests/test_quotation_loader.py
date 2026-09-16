"""QuotationLoader reference parity (GAP-006).

The legacy `QuotationNo` must carry forward as the canonical `Quotation.number`
and render `QVC{number}`, preserving exact legacy digits.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from django.utils import timezone

from accounts.models import Person
from data_migration.base import LoadReport
from data_migration.loaders.finance import QuotationLineLoader, QuotationLoader
from data_migration.loaders.reservations import ClientLoader
from data_migration.loaders.sentinels import UNKNOWN_CLIENT_LEGACY_ID
from pricing.models.currency import Currency
from properties.models.geo import Country, Region
from properties.models.property import Property
from properties.models.settings import PropertySettings
from reservations.enums import EnquirySource, QuotationStatus
from reservations.models.enquiry import Enquiry
from reservations.models.quotation import Quotation


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 10,
        "ClientDetailsId": 55,
        "AgentId": None,
        "CurrencyId": 2,
        "QuotationNo": 1805,
    }
    base.update(overrides)
    return base


@pytest.fixture
def _guest_and_currency(db: None) -> None:
    # GAP-045 D5-3: the quotation's customer is a `client-55` Person, written by
    # ClientLoader from a legacy VillaClientDetails row (Id=55); QuotationLoader
    # resolves it via `person_for_client`, no Guest in the graph.
    ClientLoader()._process_row(
        {
            "Id": 55,
            "FirstName": "Ada",
            "LastName": "Lovelace",
            "Email": "ada@example.com",
            "MobileNo": "",
        },
        LoadReport(loader="client"),
    )
    Currency.objects.create(code="GBP", name="Pound sterling", symbol="£", legacy_id="2")


@pytest.mark.django_db
def test_transform_maps_quotationno_to_number(_guest_and_currency: None) -> None:
    kwargs = QuotationLoader().transform(_row())
    assert kwargs is not None
    assert kwargs["number"] == 1805
    assert kwargs["reference"] == "QVC1805"


@pytest.mark.django_db
def test_transform_falls_back_to_id_for_reference_only(_guest_and_currency: None) -> None:
    """A missing QuotationNo keeps a numeric, customer-safe reference (`QVC{Id}`)
    but must NOT claim a `number` — the Id namespace overlaps real QuotationNos
    and the unique `number` column would collide."""
    kwargs = QuotationLoader().transform(_row(QuotationNo=None, Id=42))
    assert kwargs is not None
    assert "number" not in kwargs
    assert kwargs["reference"] == "QVC42"


@pytest.mark.django_db
def test_transform_treats_zero_quotationno_as_missing(_guest_and_currency: None) -> None:
    kwargs = QuotationLoader().transform(_row(QuotationNo=0, Id=42))
    assert kwargs is not None
    assert "number" not in kwargs
    assert kwargs["reference"] == "QVC42"


@pytest.mark.django_db
def test_transform_returns_no_currency_key(_guest_and_currency: None) -> None:
    """GAP-014: the header has no currency — each line carries its own."""
    kwargs = QuotationLoader().transform(_row())
    assert kwargs is not None
    assert "currency" not in kwargs


@pytest.mark.django_db
def test_transform_writes_person_not_guest(_guest_and_currency: None) -> None:
    """GAP-045 D5-3: the loader resolves the customer via `person_for_client`
    (the `client-{id}` Person) and writes only that `person`, not a legacy
    `guest` leg, onto the Quotation."""
    from data_migration.loaders._util import person_for_client

    kwargs = QuotationLoader().transform(_row())
    assert kwargs is not None
    assert "guest" not in kwargs
    assert kwargs["person"] == person_for_client(55)


def _line_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 77,
        "QuotationMasterId": 10,
        "VillaId": 900,
        "FromDate": date(2026, 6, 10),
        "ToDate": date(2026, 6, 17),
        "Price": 1400,
        "CurrencyId": 2,
        "IsManual": False,
    }
    base.update(overrides)
    return base


def _quotation_and_property() -> Property:
    """Build the Quotation (legacy_id=10) + Property (legacy_id=900) graph
    `QuotationLineLoader.transform` resolves against."""
    quotation = QuotationLoader().transform(_row())
    assert quotation is not None
    Quotation.objects.create(legacy_id="10", **quotation)
    country = Country.objects.get(iso2="GB")
    region = Region.objects.create(country=country, name="Cornwall", slug="cornwall")
    return Property.objects.create(
        name="P",
        display_name="P",
        slug="p",
        region=region,
        legacy_id="900",
    )


@pytest.mark.django_db
def test_line_currencyid_resolves_by_currency_legacy_id(_guest_and_currency: None) -> None:
    _quotation_and_property()
    gbp = Currency.objects.get(code="GBP")
    kwargs = QuotationLineLoader().transform(_line_row(CurrencyId=2))
    assert kwargs is not None
    assert kwargs["currency"] == gbp


@pytest.mark.django_db
def test_missing_currency_resolves_via_first_line_property(_guest_and_currency: None) -> None:
    """GAP-014: a NULL line CurrencyId resolves through the line's villa
    (settings chain), never `Currency.objects.first()`."""
    prop = _quotation_and_property()
    gbp = Currency.objects.get(code="GBP")
    PropertySettings.objects.create(property=prop, currency=gbp)
    kwargs = QuotationLineLoader().transform(_line_row(CurrencyId=None))
    assert kwargs is not None
    assert kwargs["currency"] == gbp


@pytest.mark.django_db
def test_missing_currency_terminal_default_is_eur_not_first_row(
    _guest_and_currency: None,
) -> None:
    _quotation_and_property()
    Currency.objects.create(code="AUD", name="Australian dollar", symbol="$", legacy_id="9")
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    kwargs = QuotationLineLoader().transform(_line_row(CurrencyId=None))
    assert kwargs is not None
    assert kwargs["currency"] == eur


@pytest.mark.django_db
def test_missing_currency_unresolvable_skips_row(_guest_and_currency: None) -> None:
    """No row CurrencyId, no property chain, no EUR row — the line is skipped
    rather than guessed."""
    _quotation_and_property()
    kwargs = QuotationLineLoader().transform(_line_row(CurrencyId=None))
    assert kwargs is None


# --- BUG-030 §F: occupancy, dates/expiry, notes, person, stand-ins ---

_CREATED = datetime(2024, 12, 11, 10, 13)


def test_quotation_query_selects_created_at_and_both_notes() -> None:
    query = QuotationLoader.legacy_query
    assert "q.CreatedAt" in query
    assert "q.EnquiryNote" in query
    assert "q.PreferencesNote" in query


def test_line_query_joins_the_master_occupancy() -> None:
    query = QuotationLineLoader.legacy_query
    assert "LEFT JOIN VillaQuotationMaster m ON m.Id = d.QuotationMasterId" in query
    assert "m.Adult, m.Children" in query


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("adult", "children", "expected"), [(10, 0, (10, 0)), (4, 2, (4, 2)), (None, None, (0, 0))]
)
def test_line_occupancy_comes_from_the_master(
    _guest_and_currency: None,
    adult: int | None,
    children: int | None,
    expected: tuple[int, int],
) -> None:
    _quotation_and_property()
    kwargs = QuotationLineLoader().transform(_line_row(Adult=adult, Children=children))
    assert kwargs is not None
    assert (kwargs["adults"], kwargs["children"]) == expected


@pytest.mark.django_db
def test_past_quotation_expires_a_week_after_legacy_creation(_guest_and_currency: None) -> None:
    kwargs = QuotationLoader().transform(_row(CreatedAt=_CREATED))
    assert kwargs is not None
    assert kwargs["expires_at"] == timezone.make_aware(_CREATED) + timedelta(days=7)
    assert kwargs["status"] == QuotationStatus.EXPIRED


@pytest.mark.django_db
def test_recent_quotation_stays_draft_until_its_expiry(_guest_and_currency: None) -> None:
    created = timezone.localtime().replace(tzinfo=None) - timedelta(days=1)
    kwargs = QuotationLoader().transform(_row(CreatedAt=created))
    assert kwargs is not None
    assert kwargs["expires_at"] == timezone.make_aware(created) + timedelta(days=7)
    assert kwargs["status"] == QuotationStatus.DRAFT


@pytest.mark.django_db
def test_quotation_created_at_is_backstamped(_guest_and_currency: None) -> None:
    QuotationLoader()._process_row(_row(CreatedAt=_CREATED), LoadReport(loader="quotation"))
    assert Quotation.objects.get(legacy_id="10").created_at == timezone.make_aware(_CREATED)


def _enquiry(**fields: object) -> Enquiry:
    defaults: dict[str, object] = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "legacy_id": "15",
        "inbound_message": "Looking for August.",
    }
    defaults.update(fields)
    return Enquiry.objects.create(**defaults)


@pytest.mark.django_db
def test_quotation_notes_are_appended_to_the_linked_enquiry(_guest_and_currency: None) -> None:
    enquiry = _enquiry()
    QuotationLoader()._process_row(
        _row(
            EnquireId=15,
            CreatedAt=_CREATED,
            EnquiryNote=" Wants a pool ",
            PreferencesNote="Vegan chef",
        ),
        LoadReport(loader="quotation"),
    )
    enquiry.refresh_from_db()
    assert enquiry.inbound_message == (
        "Looking for August.\n\n"
        "Quotation QVC1805 enquiry note: Wants a pool\n"
        "Quotation QVC1805 preferences note: Vegan chef"
    )


@pytest.mark.django_db
def test_blank_quotation_notes_leave_the_enquiry_message_alone(_guest_and_currency: None) -> None:
    enquiry = _enquiry()
    QuotationLoader()._process_row(
        _row(EnquireId=15, CreatedAt=_CREATED, EnquiryNote="  ", PreferencesNote=None),
        LoadReport(loader="quotation"),
    )
    enquiry.refresh_from_db()
    assert enquiry.inbound_message == "Looking for August."


@pytest.mark.django_db
def test_quotation_fills_a_missing_enquiry_person(_guest_and_currency: None) -> None:
    enquiry = _enquiry(person=None)
    QuotationLoader()._process_row(
        _row(EnquireId=15, CreatedAt=_CREATED), LoadReport(loader="quotation")
    )
    enquiry.refresh_from_db()
    assert enquiry.person == Person.objects.get(legacy_id="client-55")


@pytest.mark.django_db
def test_quotation_keeps_an_existing_enquiry_person(_guest_and_currency: None) -> None:
    other = Person.objects.create(first_name="Grace", last_name="Hopper")
    enquiry = _enquiry(person=other)
    QuotationLoader()._process_row(
        _row(EnquireId=15, CreatedAt=_CREATED), LoadReport(loader="quotation")
    )
    enquiry.refresh_from_db()
    assert enquiry.person == other


@pytest.mark.django_db
def test_agentless_stand_in_enquiry_is_dated_other_and_explained(
    _guest_and_currency: None,
) -> None:
    QuotationLoader()._process_row(
        _row(EnquireId=306, CreatedAt=_CREATED), LoadReport(loader="quotation")
    )
    stand_in = Enquiry.objects.get(legacy_id="q10-autoenquiry")
    assert stand_in.site_source == EnquirySource.OTHER
    assert stand_in.created_at == timezone.make_aware(_CREATED)
    assert "legacy quotation 10" in stand_in.inbound_message
    assert "enquiry 306" in stand_in.inbound_message


@pytest.mark.django_db
def test_agent_quote_stand_in_stays_agent_portal(_guest_and_currency: None) -> None:
    Person.objects.create(first_name="Agent", last_name="Smith", legacy_id="148")
    QuotationLoader()._process_row(
        _row(AgentId=148, EnquireId=0, CreatedAt=_CREATED), LoadReport(loader="quotation")
    )
    stand_in = Enquiry.objects.get(legacy_id="q10-autoenquiry")
    assert stand_in.site_source == EnquirySource.AGENT_PORTAL


@pytest.mark.django_db
def test_quotation_never_links_an_enquiry_to_the_unknown_client(_guest_and_currency: None) -> None:
    enquiry = _enquiry(person=None)
    QuotationLoader()._process_row(
        _row(EnquireId=15, ClientDetailsId=999, CreatedAt=_CREATED), LoadReport(loader="quotation")
    )
    assert Quotation.objects.filter(legacy_id="10").exists()  # loaded on the sentinel
    enquiry.refresh_from_db()
    assert enquiry.person is None


# --- GAP-108 U8b: quotation person falls back to its enquiry's person ---


@pytest.mark.django_db
def test_quotation_with_no_client_id_takes_its_enquiry_person(_guest_and_currency: None) -> None:
    """`ClientDetailsId = 0` used to skip the whole quotation; the customer is
    named on the enquiry behind it."""
    grace = Person.objects.create(first_name="Grace", last_name="Hopper")
    _enquiry(person=grace)
    kwargs = QuotationLoader().transform(_row(ClientDetailsId=0, EnquireId=15))
    assert kwargs is not None
    assert kwargs["person"] == grace


@pytest.mark.django_db
def test_quotation_on_a_missing_client_prefers_the_enquiry_person(
    _guest_and_currency: None,
) -> None:
    grace = Person.objects.create(first_name="Grace", last_name="Hopper")
    _enquiry(person=grace)
    kwargs = QuotationLoader().transform(_row(ClientDetailsId=999, EnquireId=15))
    assert kwargs is not None
    assert kwargs["person"] == grace


@pytest.mark.django_db
def test_quotation_prefers_its_own_client_over_the_enquiry_person(
    _guest_and_currency: None,
) -> None:
    _enquiry(person=Person.objects.create(first_name="Grace", last_name="Hopper"))
    kwargs = QuotationLoader().transform(_row(ClientDetailsId=55, EnquireId=15))
    assert kwargs is not None
    assert kwargs["person"] == Person.objects.get(legacy_id="client-55")


@pytest.mark.django_db
def test_quotation_with_no_client_and_no_enquiry_person_loads_on_the_sentinel(
    _guest_and_currency: None,
) -> None:
    """Neither side names the customer — the row LOADS on the sentinel rather
    than being dropped (it used to be skipped outright)."""
    _enquiry(person=None)
    QuotationLoader()._process_row(
        _row(ClientDetailsId=0, EnquireId=15, CreatedAt=_CREATED), LoadReport(loader="quotation")
    )
    quotation = Quotation.objects.get(legacy_id="10")
    assert quotation.person.legacy_id == UNKNOWN_CLIENT_LEGACY_ID


@pytest.mark.django_db
def test_quotation_with_no_customer_and_no_enquiry_is_skipped(_guest_and_currency: None) -> None:
    """The enquiry fallback must never mint a stand-in enquiry ON the shared
    sentinel — `_process_row` guards the linked-enquiry path for the same
    reason. With no client and no enquiry there is no customer to import."""
    assert QuotationLoader().transform(_row(ClientDetailsId=999, EnquireId=0)) is None
    assert QuotationLoader().transform(_row(ClientDetailsId=0, EnquireId=0)) is None


def test_quotation_query_is_deterministically_ordered() -> None:
    """The enquiry fallback reads `Enquiry.person`, which `_process_row`
    back-fills for an earlier quotation on the same enquiry — so the row order
    is part of the result and cannot be left to the server."""
    assert QuotationLoader.legacy_query.rstrip().endswith("ORDER BY q.Id")


# --- GAP-108 U8b: a dateless quotation line inherits the master's dates ---


def test_line_query_carries_the_master_dates() -> None:
    query = QuotationLineLoader.legacy_query
    assert "m.FromDate AS MasterFromDate" in query
    assert "m.ToDate AS MasterToDate" in query


@pytest.mark.django_db
def test_line_with_null_dates_inherits_the_master_dates(_guest_and_currency: None) -> None:
    _quotation_and_property()
    kwargs = QuotationLineLoader().transform(
        _line_row(
            FromDate=None,
            ToDate=None,
            MasterFromDate=date(2026, 7, 1),
            MasterToDate=date(2026, 7, 8),
        )
    )
    assert kwargs is not None
    assert kwargs["date_from"] == date(2026, 7, 1)
    assert kwargs["date_to"] == date(2026, 7, 8)


@pytest.mark.django_db
def test_line_half_dated_keeps_the_date_it_has(_guest_and_currency: None) -> None:
    """Only the missing half is filled — a real legacy date is never replaced."""
    _quotation_and_property()
    kwargs = QuotationLineLoader().transform(
        _line_row(
            ToDate=None,
            MasterFromDate=date(2026, 7, 1),
            MasterToDate=date(2026, 7, 8),
        )
    )
    assert kwargs is not None
    assert kwargs["date_from"] == date(2026, 6, 10)  # its own
    assert kwargs["date_to"] == date(2026, 7, 8)  # the master's


@pytest.mark.django_db
def test_line_keeps_its_own_dates_over_the_master(_guest_and_currency: None) -> None:
    _quotation_and_property()
    kwargs = QuotationLineLoader().transform(
        _line_row(MasterFromDate=date(2026, 7, 1), MasterToDate=date(2026, 7, 8))
    )
    assert kwargs is not None
    assert kwargs["date_from"] == date(2026, 6, 10)
    assert kwargs["date_to"] == date(2026, 6, 17)


@pytest.mark.django_db
def test_line_with_no_dates_on_either_side_is_skipped(_guest_and_currency: None) -> None:
    _quotation_and_property()
    assert (
        QuotationLineLoader().transform(
            _line_row(FromDate=None, ToDate=None, MasterFromDate=None, MasterToDate=None)
        )
        is None
    )
