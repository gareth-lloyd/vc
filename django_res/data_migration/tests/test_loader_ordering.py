"""BUG-029 §3: every legacy query whose keep-first outcome matters pins its
row order in SQL, so a one-shot load resolves duplicates the same way on any
dump restore (SQL Server returns unordered rows otherwise).

Where the choice is made in Python (availability recency, the country
sentinel) the behaviour is tested in the loader's own suite instead.
"""

from __future__ import annotations

from data_migration.loaders.country import CountryLoader
from data_migration.loaders.finance import CONTACT_DEFAULT_FINANCE_QUERY
from data_migration.loaders.lookups import FeatureCategoryLoader, RegionLoader
from data_migration.loaders.properties import CollectionMembershipLoader
from data_migration.loaders.property_children import NearbyPlaceLoader, PropertyImageLoader


def test_images_keep_the_lowest_id_hero_per_villa() -> None:
    # Hero de-duplication keeps the first active hero it processes.
    assert PropertyImageLoader.legacy_query.endswith("ORDER BY i.VillaId, i.Id")


def test_collection_membership_keeps_the_lowest_villa_order() -> None:
    # Duplicate (villa, collection) mappings keep the first row processed;
    # NULL VillaOrder sorts last (SQL Server sorts NULL first ascending).
    assert CollectionMembershipLoader.legacy_query.endswith(
        "ORDER BY VillaMasterId, VillaCollectionId, ISNULL(VillaOrder, 2147483647), Id"
    )


def test_country_rows_load_in_id_order() -> None:
    assert CountryLoader.legacy_query.endswith("ORDER BY Id")


def test_region_rows_load_in_id_order() -> None:
    assert RegionLoader().legacy_query.endswith("ORDER BY Id")


def test_declarative_loaders_order_by_their_pk() -> None:
    assert FeatureCategoryLoader().legacy_query.endswith("ORDER BY Id")


def test_contact_default_finance_keeps_the_lowest_id_row() -> None:
    # Money path: a contact with several default templates keeps the first.
    assert CONTACT_DEFAULT_FINANCE_QUERY.endswith("ORDER BY Id")


def test_nearby_place_type_subselect_is_ordered() -> None:
    assert "SELECT TOP 1 t.Id FROM VillaNearByLocationType t" in NearbyPlaceLoader.legacy_query
    assert "WHERE t.Code = n.PropertyNearByLocationTypeId ORDER BY t.Id)" in (
        NearbyPlaceLoader.legacy_query
    )
