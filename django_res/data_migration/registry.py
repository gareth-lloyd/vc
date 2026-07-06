"""Explicit registry of loaders, keyed by short name.

Kept manual on purpose — autodiscovery would hide load order and make
dependency-aware orchestration harder to reason about.
"""

from __future__ import annotations

from data_migration.base import Loader
from data_migration.loaders.availability import AvailabilityBlockLoader
from data_migration.loaders.bookings import (
    BookingChargeItemLoader,
    BookingLoader,
    PaymentLoader,
)
from data_migration.loaders.country import CountryLoader
from data_migration.loaders.defaults import PropertyDefaultsLoader
from data_migration.loaders.finance import (
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
    # Singleton config — needs CurrencyLoader (resolves the default currency
    # by legacy_id) but nothing downstream depends on it.
    PropertyDefaultsLoader.name: PropertyDefaultsLoader,
    UserLoader.name: UserLoader,
    ContactLoader.name: ContactLoader,
    ContactEmailLoader.name: ContactEmailLoader,
    ContactPhoneLoader.name: ContactPhoneLoader,
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
    QuotationLoader.name: QuotationLoader,
    QuotationLineLoader.name: QuotationLineLoader,
    BookingLoader.name: BookingLoader,
    PaymentLoader.name: PaymentLoader,
    # Charge lines resolve their parent Booking by legacy_id, so they must
    # follow BookingLoader; they run after PaymentLoader so legacy payment
    # rows are already in place when the load (with the booking_total_changed
    # resync suppressed) writes on top of them.
    BookingChargeItemLoader.name: BookingChargeItemLoader,
    # After the booking loaders: the availability-block loader skips any run
    # whose range an imported booking already occupies, so the imported
    # occupancy must be in place before it runs.
    AvailabilityBlockLoader.name: AvailabilityBlockLoader,
    # External-ID backfill — registered last so every domain target row
    # (Property/Person/Enquiry/Quotation/Booking) already carries its
    # legacy_id when SyncRecord rows are written.
    SyncRecordZohoLoader.name: SyncRecordZohoLoader,
}
