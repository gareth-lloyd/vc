"""URL configuration for the properties app."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, path
from rest_framework.routers import DefaultRouter

from properties.views import (
    ChangeOverRuleDetailView,
    CollectionViewSet,
    CountryViewSet,
    FeatureCategoryViewSet,
    FeatureViewSet,
    GroupFinanceView,
    GroupSettingsView,
    NearbyPlaceTypeViewSet,
    PropertyCapacityView,
    PropertyCategoryViewSet,
    PropertyChangeOverRuleListCreateView,
    PropertyCollectionsView,
    PropertyContactAssignmentDetailView,
    PropertyContactAssignmentListCreateView,
    PropertyDescriptionDetailView,
    PropertyDescriptionListView,
    PropertyFinanceView,
    PropertyGroupViewSet,
    PropertyImageDetailView,
    PropertyImageListCreateView,
    PropertyImageReorderView,
    PropertyImageSetHeroView,
    PropertyLocationView,
    PropertyNearbyPlaceDetailView,
    PropertyNearbyPlaceListCreateView,
    PropertyPriceDisplayView,
    PropertyRoomListCreateView,
    PropertyRoomReorderView,
    PropertySettingsView,
    PropertyViewSet,
    RegionViewSet,
    RoomDetailView,
)
from properties.views.collection import (
    CollectionMembershipDetailView,
    CollectionPropertiesView,
)

router = DefaultRouter(trailing_slash=False)
router.register(r"properties", PropertyViewSet, basename="property")
router.register(r"property-categories", PropertyCategoryViewSet, basename="property-category")
router.register(r"property-groups", PropertyGroupViewSet, basename="property-group")
router.register(r"collections", CollectionViewSet, basename="collection")
router.register(r"features", FeatureViewSet, basename="feature")
router.register(r"feature-categories", FeatureCategoryViewSet, basename="feature-category")
router.register(r"regions", RegionViewSet, basename="region")
router.register(r"countries", CountryViewSet, basename="country")
router.register(r"nearby-place-types", NearbyPlaceTypeViewSet, basename="nearby-place-type")

# Action endpoints + nested sub-resources. The colon-verb form is registered
# explicitly because DRF's DefaultRouter doesn't generate it.
_property_actions: list[URLPattern] = [
    path(
        "properties/<str:pk>:activate",
        PropertyViewSet.as_view({"post": "activate"}),
        name="property-activate",
    ),
    path(
        "properties/<str:pk>:archive",
        PropertyViewSet.as_view({"post": "archive"}),
        name="property-archive",
    ),
    path(
        "properties/<str:pk>:restore",
        PropertyViewSet.as_view({"post": "restore"}),
        name="property-restore",
    ),
    path(
        "properties/<str:pk>:duplicate",
        PropertyViewSet.as_view({"post": "duplicate"}),
        name="property-duplicate",
    ),
    path(
        "properties/<int:pk>:import-from-zoho",
        PropertyViewSet.as_view({"post": "import_from_zoho"}),
        name="property-import-from-zoho",
    ),
]

_property_subresources: list[URLPattern] = [
    path(
        "properties/<int:property_id>/images",
        PropertyImageListCreateView.as_view(),
        name="property-image-list",
    ),
    path(
        "properties/<int:property_id>/images/<int:image_id>",
        PropertyImageDetailView.as_view(),
        name="property-image-detail",
    ),
    path(
        "properties/<int:property_id>/images:reorder",
        PropertyImageReorderView.as_view(),
        name="property-image-reorder",
    ),
    path(
        "properties/<int:property_id>/images:set-hero",
        PropertyImageSetHeroView.as_view(),
        name="property-image-set-hero",
    ),
    path(
        "properties/<int:property_id>/rooms",
        PropertyRoomListCreateView.as_view(),
        name="property-room-list",
    ),
    path(
        "properties/<int:property_id>/rooms/<int:room_id>",
        RoomDetailView.as_view(),
        name="property-room-detail",
    ),
    path(
        "properties/<int:property_id>/rooms:reorder",
        PropertyRoomReorderView.as_view(),
        name="property-room-reorder",
    ),
    path(
        "properties/<int:property_id>/descriptions",
        PropertyDescriptionListView.as_view(),
        name="property-description-list",
    ),
    path(
        "properties/<int:property_id>/descriptions/<str:section>",
        PropertyDescriptionDetailView.as_view(),
        name="property-description-detail",
    ),
    path(
        "properties/<int:property_id>/nearby",
        PropertyNearbyPlaceListCreateView.as_view(),
        name="property-nearby-list",
    ),
    path(
        "properties/<int:property_id>/nearby/<int:poi_id>",
        PropertyNearbyPlaceDetailView.as_view(),
        name="property-nearby-detail",
    ),
    path(
        "properties/<int:property_id>/change-over-rules",
        PropertyChangeOverRuleListCreateView.as_view(),
        name="property-changeover-list",
    ),
    path(
        "change-over-rules/<int:pk>",
        ChangeOverRuleDetailView.as_view(),
        name="changeover-detail",
    ),
    path(
        "properties/<int:property_id>/contacts",
        PropertyContactAssignmentListCreateView.as_view(),
        name="property-contact-list",
    ),
    path(
        "properties/<int:property_id>/contacts/<int:mapping_id>",
        PropertyContactAssignmentDetailView.as_view(),
        name="property-contact-detail",
    ),
    path(
        "properties/<int:property_id>/settings",
        PropertySettingsView.as_view(),
        name="property-settings",
    ),
    path(
        "properties/<int:property_id>/finance",
        PropertyFinanceView.as_view(),
        name="property-finance",
    ),
    path(
        "properties/<int:property_id>/location",
        PropertyLocationView.as_view(),
        name="property-location",
    ),
    path(
        "properties/<int:property_id>/capacity",
        PropertyCapacityView.as_view(),
        name="property-capacity",
    ),
    path(
        "properties/<int:property_id>/price-display",
        PropertyPriceDisplayView.as_view(),
        name="property-price-display",
    ),
    path(
        "properties/<int:property_id>/collections",
        PropertyCollectionsView.as_view(),
        name="property-collections",
    ),
    path(
        "properties/<int:property_id>/collections/<str:collection>",
        CollectionMembershipDetailView.as_view(),
        name="property-collection-membership",
    ),
    path(
        "property-groups/<int:group_id>/settings",
        GroupSettingsView.as_view(),
        name="property-group-settings",
    ),
    path(
        "property-groups/<int:group_id>/finance",
        GroupFinanceView.as_view(),
        name="property-group-finance",
    ),
    path(
        "collections/<slug:slug>/properties",
        CollectionPropertiesView.as_view(),
        name="collection-properties",
    ),
]


urlpatterns: list[URLPattern | URLResolver] = [
    *_property_actions,
    *_property_subresources,
    *router.urls,
]
