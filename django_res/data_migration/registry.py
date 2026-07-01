"""Explicit registry of loaders, keyed by short name.

Kept manual on purpose — autodiscovery would hide load order and make
dependency-aware orchestration harder to reason about.
"""

from __future__ import annotations

from data_migration.base import Loader
from data_migration.loaders.bookings import BookingLoader, PaymentLoader
from data_migration.loaders.country import CountryLoader
from data_migration.loaders.finance import (
    GroupFinanceLoader,
    PropertyFinanceLoader,
    QuotationLineLoader,
    QuotationLoader,
)
from data_migration.loaders.integrations import SyncRecordZohoLoader
from data_migration.loaders.lookups import (
    CurrencyLoader,
    FeatureCategoryLoader,
    FeatureLoader,
    NearbyPlaceTypeLoader,
    PropertyCategoryLoader,
    RegionLoader,
)
from data_migration.loaders.people import (
    ContactEmailLoader,
    ContactLoader,
    ContactPhoneLoader,
    UserLoader,
)
from data_migration.loaders.preferences import (
    GuestPreferenceLoader,
    GuestPreferenceTypeLoader,
)
from data_migration.loaders.pricing import RateBandLoader, RatePlanLoader
from data_migration.loaders.properties import (
    CollectionLoader,
    CollectionMembershipLoader,
    PropertyGroupLoader,
    PropertyLoader,
)
from data_migration.loaders.property_children import (
    NearbyPlaceLoader,
    PropertyFeatureMappingLoader,
    PropertyImageLoader,
    RoomLoader,
)
from data_migration.loaders.reservations import (
    ClientLoader,
    EnquiryLoader,
    PropertyContactAssignmentLoader,
)

LOADERS: dict[str, type[Loader]] = {
    CountryLoader.name: CountryLoader,
    RegionLoader.name: RegionLoader,
    CurrencyLoader.name: CurrencyLoader,
    PropertyCategoryLoader.name: PropertyCategoryLoader,
    NearbyPlaceTypeLoader.name: NearbyPlaceTypeLoader,
    FeatureCategoryLoader.name: FeatureCategoryLoader,
    FeatureLoader.name: FeatureLoader,
    UserLoader.name: UserLoader,
    ContactLoader.name: ContactLoader,
    ContactEmailLoader.name: ContactEmailLoader,
    ContactPhoneLoader.name: ContactPhoneLoader,
    PropertyGroupLoader.name: PropertyGroupLoader,
    PropertyLoader.name: PropertyLoader,
    CollectionLoader.name: CollectionLoader,
    CollectionMembershipLoader.name: CollectionMembershipLoader,
    RoomLoader.name: RoomLoader,
    PropertyImageLoader.name: PropertyImageLoader,
    NearbyPlaceLoader.name: NearbyPlaceLoader,
    PropertyFeatureMappingLoader.name: PropertyFeatureMappingLoader,
    RatePlanLoader.name: RatePlanLoader,
    RateBandLoader.name: RateBandLoader,
    PropertyContactAssignmentLoader.name: PropertyContactAssignmentLoader,
    # ClientLoader (VillaClientDetails → Person, keyed `client-{id}`) MUST stay
    # ahead of preferences / finance / booking: those loaders resolve the
    # customer via `person_for_client`, so the `client-{id}` Persons must already
    # exist when they run.
    ClientLoader.name: ClientLoader,
    GuestPreferenceTypeLoader.name: GuestPreferenceTypeLoader,
    GuestPreferenceLoader.name: GuestPreferenceLoader,
    EnquiryLoader.name: EnquiryLoader,
    PropertyFinanceLoader.name: PropertyFinanceLoader,
    GroupFinanceLoader.name: GroupFinanceLoader,
    QuotationLoader.name: QuotationLoader,
    QuotationLineLoader.name: QuotationLineLoader,
    BookingLoader.name: BookingLoader,
    PaymentLoader.name: PaymentLoader,
    # External-ID backfill — registered last so every domain target row
    # (Property/Person/Enquiry/Quotation/Booking) already carries its
    # legacy_id when SyncRecord rows are written.
    SyncRecordZohoLoader.name: SyncRecordZohoLoader,
}
