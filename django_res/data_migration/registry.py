"""Explicit registry of loaders, keyed by short name.

Kept manual on purpose — autodiscovery would hide load order and make
dependency-aware orchestration harder to reason about.
"""

from __future__ import annotations

from data_migration.base import Loader
from data_migration.loaders.availability import AvailabilityBlockLoader
from data_migration.loaders.country import CountryLoader
from data_migration.loaders.defaults import PropertyDefaultsLoader
from data_migration.loaders.extras import ExtraLoader
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
    # Extras catalogue (GAP-107) resolves its currency through the villa's
    # live rate plans, so it follows the rate loaders.
    ExtraLoader.name: ExtraLoader,
    PropertyContactAssignmentLoader.name: PropertyContactAssignmentLoader,
    # ClientLoader (VillaClientDetails → Person, keyed `client-{id}`) MUST stay
    # ahead of preferences / finance: those loaders resolve the customer via
    # `person_for_client`, so the `client-{id}` Persons must already exist when
    # they run.
    ClientLoader.name: ClientLoader,
    EnquiryLoader.name: EnquiryLoader,
    PropertyFinanceLoader.name: PropertyFinanceLoader,
    QuotationLoader.name: QuotationLoader,
    QuotationLineLoader.name: QuotationLineLoader,
    # Preferences resolve an OPTIONAL Quotation by legacy_id, so they must
    # follow QuotationLoader. When they ran before it (pre-2026-07-05), a
    # quotation-linked preference resolved `quotation=None` on a fresh single
    # pass — either mis-linked or swallowed by the (person, type, quotation)
    # duplicate collapse — and only converged on the SECOND full run (caught
    # by the dry-run double-run check; see DRYRUN_LOG.md).
    GuestPreferenceTypeLoader.name: GuestPreferenceTypeLoader,
    GuestPreferenceLoader.name: GuestPreferenceLoader,
    # Booking / Payment / BookingChargeItem loaders (`loaders/bookings.py`) are
    # deliberately UNREGISTERED (GAP-089, GAP-108): bookings come from the Past
    # Bookers sheet (`import_past_bookers`), not `VillaBooking`. The modules and
    # their tests stay as the legacy-schema record; `reconcile_legacy` asserts
    # no row carrying a legacy_id ever lands in those tables.
    #
    # The availability-block loader skips any run whose range an existing
    # booking already occupies; with no legacy bookings loaded that is only
    # ever a booking written before it runs.
    AvailabilityBlockLoader.name: AvailabilityBlockLoader,
    # External-ID backfill — registered last so every domain target row
    # (Property/Person/Enquiry/Quotation) already carries its legacy_id when
    # SyncRecord rows are written.
    SyncRecordZohoLoader.name: SyncRecordZohoLoader,
}
