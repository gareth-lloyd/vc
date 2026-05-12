from __future__ import annotations

from django.contrib import admin

from properties.models import (
    ChangeOverRule,
    Collection,
    CollectionMembership,
    Country,
    Feature,
    FeatureCategory,
    GroupSettings,
    NearbyPlaceType,
    Property,
    PropertyCapacity,
    PropertyCategory,
    PropertyContactAssignment,
    PropertyDescription,
    PropertyGroup,
    PropertyImage,
    PropertyLocation,
    PropertyNearbyPlace,
    PropertySettings,
    Region,
    Room,
    RoomBeds,
)

admin.site.register(Country)
admin.site.register(Region)
admin.site.register(NearbyPlaceType)
admin.site.register(PropertyNearbyPlace)
admin.site.register(PropertyCategory)
admin.site.register(PropertyGroup)
admin.site.register(Property)
admin.site.register(PropertyLocation)
admin.site.register(PropertyCapacity)
admin.site.register(PropertySettings)
admin.site.register(GroupSettings)
admin.site.register(PropertyDescription)
admin.site.register(Room)
admin.site.register(RoomBeds)
admin.site.register(PropertyImage)
admin.site.register(FeatureCategory)
admin.site.register(Feature)
admin.site.register(Collection)
admin.site.register(CollectionMembership)
admin.site.register(PropertyContactAssignment)
admin.site.register(ChangeOverRule)
