"""WordPress enquiry intake — tolerant serializer + creation service.

The REAL wire shape is recoverable from `ResSystem/vc_wp_1.sql` (201 stored
submissions): `Properties` is a string id with `"0"` = none-selected,
`RegionIds` a list of string ids (same sentinel), ints arrive as strings,
`EnquireDateTypeString` carries UI labels ("Specific dates", "+/- 3 days",
"Flexible") while the int `EnquireDateType` is unreliable (7 accompanies both
"Specific dates" and "Flexible"), and `CountryIds`/`UserFeedback`/`other_text`
exist. The serializer still tolerates the .NET DTO + Postman variants, and the
service never rejects a lead over a mapping miss — unresolvable values are
preserved as bracketed suffixes on `inbound_message`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from properties.factories import PropertyFactory, RegionFactory
from properties.models import Country
from reservations.enums import EnquiryRequestType, EnquirySource, EnquiryStatus, LeadStatus
from reservations.models import Enquiry
from reservations.serializers.wordpress import WordPressEnquirySerializer
from reservations.services.wordpress_intake import (
    create_enquiry_from_wordpress,
    derive_idempotency_key,
)

pytestmark = pytest.mark.django_db


def _legacy_country(legacy_id: str) -> Country:
    # Countries are migration-seeded; stamp the legacy bridge id on Greece.
    country = Country.objects.get(iso2="GR")
    country.legacy_id = legacy_id
    country.save(update_fields=["legacy_id"])
    return country


def _create(payload: dict[str, object]) -> Enquiry:
    serializer = WordPressEnquirySerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    return create_enquiry_from_wordpress(serializer.validated_data)


def test_postman_shape_payload_maps_fully() -> None:
    villa = PropertyFactory(legacy_id="1042")

    enquiry = _create(
        {
            "FirstName": "Ana",
            "LastName": "Silva",
            "Email": "ana@example.com",
            "CountryCode": "+44",
            "ContactNo": "07911 123456",
            "PropertyId": 1042,
            "EnquireDateType": 1,
            "FromDate": "2026-11-01",
            "ToDate": "2026-11-08",
            "MinBed": 3,
            "MaxBed": 5,
            "Adults": 4,
            "Children": 2,
            "Notes": "Family trip",
            "RequestType": "ENQUIRY",
            "referral": "friend",
        }
    )

    assert enquiry.first_name == "Ana"
    assert enquiry.last_name == "Silva"
    assert enquiry.email == "ana@example.com"
    assert enquiry.phone == "+447911123456"
    assert enquiry.property == villa
    assert str(enquiry.date_from) == "2026-11-01"
    assert str(enquiry.date_to) == "2026-11-08"
    assert enquiry.is_flexible is False
    assert enquiry.min_bedrooms == 3
    assert enquiry.adults == 4
    assert enquiry.children == 2
    assert enquiry.request_type == EnquiryRequestType.QUOTE
    assert enquiry.referral_code == "friend"
    assert enquiry.site_source == EnquirySource.MAIN_WEBSITE
    assert enquiry.status == EnquiryStatus.NEW
    assert enquiry.lead_status == LeadStatus.WARM
    assert enquiry.person is None
    assert "Family trip" in enquiry.inbound_message


def test_dotnet_dto_shape_payload_maps_fully() -> None:
    villa = PropertyFactory(legacy_id="77")

    enquiry = _create(
        {
            "FirstName": "Bo",
            "Email": "bo@example.com",
            "Properties": "77",
            "EnquireDateTypeString": "ThreeDays",
            "FromDate": "2026-07-04",
            "ToDate": "2026-07-11",
        }
    )

    assert enquiry.property == villa
    assert enquiry.is_flexible is True
    assert enquiry.flexibility_days == 3


def test_unresolvable_property_csv_is_preserved_not_dropped() -> None:
    enquiry = _create({"Email": "x@example.com", "Properties": "12,13"})

    assert enquiry.property is None
    assert "[property: 12,13]" in enquiry.inbound_message


def test_unknown_property_id_is_preserved_not_dropped() -> None:
    enquiry = _create({"Email": "x@example.com", "PropertyId": 999999})

    assert enquiry.property is None
    assert "[property: 999999]" in enquiry.inbound_message


def test_single_region_id_resolves_by_legacy_id() -> None:
    region = RegionFactory(legacy_id="9")

    enquiry = _create({"Email": "x@example.com", "RegionIds": [9]})

    assert enquiry.region == region


def test_multiple_region_ids_are_preserved_not_dropped() -> None:
    RegionFactory(legacy_id="9")

    enquiry = _create({"Email": "x@example.com", "RegionIds": [9, 10]})

    assert enquiry.region is None
    assert "[regions: 9,10]" in enquiry.inbound_message


def test_null_region_id_entries_are_tolerated() -> None:
    # The WP contact + wishlist forms have no RegionIds input; the theme's
    # ajax handler wraps the missing key into array(null), so the wire shape
    # is "RegionIds": [null]. Must behave like the "0" sentinel: no region,
    # no leftover suffix, lead still created.
    enquiry = _create({"Email": "x@example.com", "RegionIds": [None]})

    assert enquiry.region is None
    assert "[regions:" not in enquiry.inbound_message


def test_wide_flexibility_clamps_to_model_max_and_preserves_raw() -> None:
    enquiry = _create({"Email": "x@example.com", "EnquireDateType": 7})

    assert enquiry.is_flexible is True
    assert enquiry.flexibility_days == 3  # model validator caps at 3
    assert "[date flexibility: SevenDays]" in enquiry.inbound_message


def test_whole_days_string_clamps_too() -> None:
    enquiry = _create({"Email": "x@example.com", "EnquireDateTypeString": "WholeDays"})

    assert enquiry.is_flexible is True
    assert enquiry.flexibility_days == 3
    assert "[date flexibility: WholeDays]" in enquiry.inbound_message


def test_wishlist_maps_to_other_with_raw_preserved() -> None:
    enquiry = _create({"Email": "x@example.com", "RequestType": "WISHLIST"})

    assert enquiry.request_type == EnquiryRequestType.OTHER
    assert "[request type: WISHLIST]" in enquiry.inbound_message


def test_unrecognised_request_type_maps_to_other_with_raw_preserved() -> None:
    enquiry = _create({"Email": "x@example.com", "RequestType": "SOMETHING_NEW"})

    assert enquiry.request_type == EnquiryRequestType.OTHER
    assert "[request type: SOMETHING_NEW]" in enquiry.inbound_message


def test_marketing_opt_in_is_captured() -> None:
    enquiry = _create({"Email": "x@example.com", "IsSignUp": True})

    assert "[marketing opt-in: yes]" in enquiry.inbound_message


def test_geo_strings_are_preserved() -> None:
    enquiry = _create(
        {"Email": "x@example.com", "CountryId": "3", "Countries": "Greece", "Regions": "Corfu"}
    )

    assert "[country: 3]" in enquiry.inbound_message
    assert "[countries: Greece]" in enquiry.inbound_message
    assert "[region names: Corfu]" in enquiry.inbound_message


def test_inverted_dates_are_swapped() -> None:
    enquiry = _create({"Email": "x@example.com", "FromDate": "2026-11-08", "ToDate": "2026-11-01"})

    assert str(enquiry.date_from) == "2026-11-01"
    assert str(enquiry.date_to) == "2026-11-08"


def test_minimal_payload_still_creates_a_lead() -> None:
    enquiry = _create({})

    assert enquiry.pk is not None
    assert enquiry.site_source == EnquirySource.MAIN_WEBSITE
    assert enquiry.reference.startswith("E")


def test_unknown_extra_keys_are_tolerated() -> None:
    # ASP.NET silently dropped unknown keys; the WP plugin may send anything.
    enquiry = _create({"Email": "x@example.com", "RefNo": 5, "CollectionIds": [1, 2]})

    assert enquiry.email == "x@example.com"


def test_real_wire_shape_payload_maps_fully() -> None:
    # Field-for-field the shape stored in vc_wp_1.sql (values anonymised):
    # string ints, UI-label date type, "0" sentinels, CountryIds CSV.
    villa = PropertyFactory(legacy_id="258")
    greece = _legacy_country("1")

    enquiry = _create(
        {
            "FirstName": "Pat",
            "LastName": "Example",
            "Email": "pat@example.com",
            "CountryCode": "+44",
            "ContactNo": "07911123456",
            "Properties": "258",
            "RegionIds": ["14"],
            "FromDate": "2026-08-15",
            "ToDate": "2026-08-29",
            "EnquireDateType": 7,
            "EnquireDateTypeString": "Specific dates",
            "CountryIds": "1",
            "MinBed": "5",
            "MaxBed": "0",
            "Adults": "7",
            "Children": "1",
            "Notes": "Looking for a villa with a pool.",
            "referral": "",
            "UserFeedback": "Google/Online Search",
            "other_text": "Other",
            "IsSignUp": True,
        }
    )

    assert enquiry.property == villa
    assert enquiry.phone == "+447911123456"
    # int 7 + "Specific dates": the string is authoritative — NOT flexible.
    assert enquiry.is_flexible is False
    assert enquiry.flexibility_days == 0
    assert enquiry.min_bedrooms == 5
    assert enquiry.adults == 7
    assert enquiry.children == 1
    assert f"[countries: {greece.name}]" in enquiry.inbound_message
    assert "[heard via: Google/Online Search]" in enquiry.inbound_message
    assert "[marketing opt-in: yes]" in enquiry.inbound_message
    # "0" sentinels and other_text=="Other" leave no junk suffixes.
    assert "[date flexibility" not in enquiry.inbound_message
    assert "[max bedrooms" not in enquiry.inbound_message


def test_real_string_date_labels_map_without_the_unreliable_int() -> None:
    plus_minus = _create({"EnquireDateType": 3, "EnquireDateTypeString": "+/- 3 days"})
    flexible = _create({"EnquireDateType": 7, "EnquireDateTypeString": "Flexible"})

    assert (plus_minus.is_flexible, plus_minus.flexibility_days) == (True, 3)
    assert "[date flexibility" not in plus_minus.inbound_message
    assert (flexible.is_flexible, flexible.flexibility_days) == (True, 3)
    assert "[date flexibility: Flexible]" in flexible.inbound_message  # clamped


def test_zero_sentinels_mean_none_selected_not_a_mapping_miss() -> None:
    enquiry = _create(
        {"Email": "x@example.com", "Properties": "0", "RegionIds": ["0"], "PropertyId": 0}
    )

    assert enquiry.property is None
    assert enquiry.region is None
    assert "[property" not in enquiry.inbound_message
    assert "[regions" not in enquiry.inbound_message


def test_country_ids_resolve_to_names_with_raw_fallback() -> None:
    _legacy_country("1")

    enquiry = _create({"Email": "x@example.com", "CountryIds": "3,1,2"})

    # 1 resolves; 3 and 2 fall back to their raw ids.
    assert "[countries: 3, Greece, 2]" in enquiry.inbound_message


def test_heard_via_detail_is_kept_when_it_says_something() -> None:
    enquiry = _create(
        {
            "Email": "x@example.com",
            "UserFeedback": "Other (please specify)",
            "other_text": "A friend's wedding",
        }
    )

    assert "[heard via: Other (please specify)]" in enquiry.inbound_message
    assert "[heard via detail: A friend's wedding]" in enquiry.inbound_message


def test_positive_max_bed_is_preserved() -> None:
    enquiry = _create({"Email": "x@example.com", "MinBed": 3, "MaxBed": 6})

    assert enquiry.min_bedrooms == 3
    assert "[max bedrooms: 6]" in enquiry.inbound_message


def test_overlong_free_text_is_truncated_not_rejected() -> None:
    enquiry = _create({"FirstName": "x" * 300, "ContactNo": "not a number " * 10})

    assert enquiry.pk is not None
    assert len(enquiry.first_name) == 128
    assert len(enquiry.phone) <= 32


def test_idempotency_key_is_stable_within_a_time_bucket() -> None:
    now = datetime(2026, 7, 26, 14, 10, tzinfo=UTC)
    payload = {"Email": "x@example.com", "Adults": 2}

    key_a = derive_idempotency_key(payload, now=now)
    key_b = derive_idempotency_key(
        {"Adults": 2, "Email": "x@example.com"}, now=now + timedelta(minutes=40)
    )

    assert key_a == key_b  # key order and sub-hour timing don't matter
    assert len(key_a) <= 128


def test_idempotency_key_varies_across_payloads_and_buckets() -> None:
    now = datetime(2026, 7, 26, 14, 10, tzinfo=UTC)
    payload = {"Email": "x@example.com"}

    assert derive_idempotency_key(payload, now=now) != derive_idempotency_key(
        {"Email": "y@example.com"}, now=now
    )
    assert derive_idempotency_key(payload, now=now) != derive_idempotency_key(
        payload, now=now + timedelta(hours=1)
    )
