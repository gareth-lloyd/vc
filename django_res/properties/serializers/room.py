"""Serializer for `Room` (plus inline bed-config write surface)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from properties.models import Room, RoomBeds


class _RoomBedsSerializer(serializers.ModelSerializer[RoomBeds]):
    class Meta:
        model = RoomBeds
        fields = [
            "double",
            "twin_double",
            "twin",
            "single",
            "bunk",
            "sofa",
            "childrens",
        ]


class RoomSerializer(serializers.ModelSerializer[Room]):
    """Room with inline bed config. Accepts `beds` on write; nested upsert."""

    beds = _RoomBedsSerializer(required=False)

    class Meta:
        model = Room
        fields = [
            "id",
            "property",
            "name",
            "placement",
            "website_description",
            "vc_notes",
            "is_ensuite",
            "sort_order",
            "beds",
        ]
        read_only_fields = ["id", "property"]

    def create(self, validated_data: dict[str, Any]) -> Room:
        beds_data = validated_data.pop("beds", None)
        room = Room.objects.create(**validated_data)
        if beds_data:
            RoomBeds.objects.create(room=room, **beds_data)
        else:
            RoomBeds.objects.create(room=room)
        return room

    def update(self, instance: Room, validated_data: dict[str, Any]) -> Room:
        beds_data = validated_data.pop("beds", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if beds_data is not None:
            RoomBeds.objects.update_or_create(room=instance, defaults=beds_data)
        return instance
