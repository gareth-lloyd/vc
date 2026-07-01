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
    PropertyCalendarFeed,
    PropertyCapacity,
    PropertyCategory,
    PropertyContactAssignment,
    PropertyDescription,
    PropertyGroup,
    PropertyImage,
    PropertyLocation,
    PropertyNearbyPlace,
    PropertyService,
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
admin.site.register(PropertyService)


@admin.register(PropertyCalendarFeed)
class PropertyCalendarFeedAdmin(admin.ModelAdmin):
    # `url` is a capability URL (secret token) — keep it off list/search views.
    # It stays editable on the detail form so ops can paste / rotate it.
    list_display = (
        "id",
        "property",
        "platform",
        "label",
        "is_active",
        "last_status",
        "last_polled_at",
    )
    list_filter = ("platform", "is_active", "last_status")
    list_select_related = ("property",)
    readonly_fields = ("last_polled_at", "last_status", "last_error")
