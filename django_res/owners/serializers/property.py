"""Read-only owner-facing property representation.

Deliberately trimmed: an owner sees catalogue facts about their own villa
(name, status, location, headline capacity, hero image) but none of the
finance / owner-contact / rate detail the staff serializers expose.
"""

from __future__ import annotations

from rest_framework import serializers

from properties.models import Property, PropertyCapacity


class OwnerPropertySerializer(serializers.ModelSerializer[Property]):
    guests = serializers.SerializerMethodField()
    bedrooms = serializers.SerializerMethodField()
    hero_image_url = serializers.SerializerMethodField()
    can_request_block = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            "id",
            "name",
            "display_name",
            "slug",
            "status",
            "category",
            "group",
            "region",
            "guests",
            "bedrooms",
            "hero_image_url",
            "can_request_block",
        ]

    def get_can_request_block(self, obj: Property) -> bool:
        # The view places the role-scoped writable set in context; default empty
        # so a serializer used without it never claims the capability.
        return obj.id in self.context.get("block_writer_property_ids", set())

    @staticmethod
    def _capacity(obj: Property) -> PropertyCapacity | None:
        try:
            return obj.capacity
        except PropertyCapacity.DoesNotExist:
            return None

    def get_guests(self, obj: Property) -> int | None:
        cap = self._capacity(obj)
        return cap.guests if cap else None

    def get_bedrooms(self, obj: Property) -> int | None:
        cap = self._capacity(obj)
        return cap.bedrooms if cap else None

    def get_hero_image_url(self, obj: Property) -> str | None:
        # `images` is prefetched to active HERO rows only (see the viewset).
        heroes = list(obj.images.all())
        if not heroes:
            return None
        url = heroes[0].image.url
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request is not None else url
