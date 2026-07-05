"""Properties app DRF views — re-export for the URL module."""

from __future__ import annotations

from properties.views.capacity import PropertyCapacityView
from properties.views.changeover import (
    ChangeOverRuleDetailView,
    PropertyChangeOverRuleListCreateView,
)
from properties.views.collection import (
    CollectionMembershipDetailView,
    CollectionViewSet,
    PropertyCollectionsView,
)
from properties.views.contact_assignment import (
    PropertyContactAssignmentDetailView,
    PropertyContactAssignmentListCreateView,
)
from properties.views.description import (
    PropertyDescriptionDetailView,
    PropertyDescriptionListView,
)
from properties.views.feature import FeatureCategoryViewSet, FeatureViewSet
from properties.views.finance import (
    GroupFinanceView,
    PropertyFinanceView,
)
from properties.views.geo import (
    CountryViewSet,
    NearbyPlaceTypeViewSet,
    PropertyNearbyPlaceDetailView,
    PropertyNearbyPlaceListCreateView,
    RegionViewSet,
)
from properties.views.image import (
    PropertyImageDetailView,
    PropertyImageListCreateView,
    PropertyImageReorderView,
    PropertyImageSetHeroView,
)
from properties.views.location import PropertyLocationView
from properties.views.metadata import (
    PropertyCategoryViewSet,
    PropertyGroupViewSet,
)
from properties.views.price_display import PropertyPriceDisplayView
from properties.views.property import PropertyViewSet
from properties.views.room import (
    PropertyRoomListCreateView,
    PropertyRoomReorderView,
    RoomAttributeViewSet,
    RoomDetailView,
)
from properties.views.service import (
    PropertyServiceDetailView,
    PropertyServiceListCreateView,
)
from properties.views.settings import (
    GroupSettingsView,
    PropertySettingsView,
)

__all__ = [
    "ChangeOverRuleDetailView",
    "CollectionMembershipDetailView",
    "CollectionViewSet",
    "CountryViewSet",
    "FeatureCategoryViewSet",
    "FeatureViewSet",
    "GroupFinanceView",
    "GroupSettingsView",
    "NearbyPlaceTypeViewSet",
    "PropertyCapacityView",
    "PropertyCategoryViewSet",
    "PropertyChangeOverRuleListCreateView",
    "PropertyCollectionsView",
    "PropertyContactAssignmentDetailView",
    "PropertyContactAssignmentListCreateView",
    "PropertyDescriptionDetailView",
    "PropertyDescriptionListView",
    "PropertyFinanceView",
    "PropertyGroupViewSet",
    "PropertyImageDetailView",
    "PropertyImageListCreateView",
    "PropertyImageReorderView",
    "PropertyImageSetHeroView",
    "PropertyLocationView",
    "PropertyNearbyPlaceDetailView",
    "PropertyNearbyPlaceListCreateView",
    "PropertyPriceDisplayView",
    "PropertyRoomListCreateView",
    "PropertyRoomReorderView",
    "PropertyServiceDetailView",
    "PropertyServiceListCreateView",
    "PropertySettingsView",
    "PropertyViewSet",
    "RegionViewSet",
    "RoomAttributeViewSet",
    "RoomDetailView",
]
