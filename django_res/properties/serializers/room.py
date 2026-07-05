"""Serializers for `Room` (plus inline bed-config and amenity-link write
surfaces) and the `RoomAttribute` catalog."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from rest_framework import serializers

from properties.models import Room, RoomAttribute, RoomAttributeAssignment, RoomBeds


class RoomAttributeSerializer(serializers.ModelSerializer[RoomAttribute]):
    class Meta:
        model = RoomAttribute
        fields = [
            "id",
            "slug",
            "name",
            "description",
            "icon",
            "sort_order",
            "is_active",
            "implies_property_feature",
        ]


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


class _RoomAttributeLinkSerializer(serializers.ModelSerializer[RoomAttributeAssignment]):
    """One amenity link. Write shape is `{attribute: <id>, note?}`; reads add
    the catalog row's display fields (incl. `is_active` so the form can badge
    retired-but-assigned rows instead of silently dropping them)."""

    attribute = serializers.PrimaryKeyRelatedField(queryset=RoomAttribute.objects.all())
    slug = serializers.SlugField(source="attribute.slug", read_only=True)
    name = serializers.CharField(source="attribute.name", read_only=True)
    icon = serializers.CharField(source="attribute.icon", read_only=True)
    is_active = serializers.BooleanField(source="attribute.is_active", read_only=True)

    class Meta:
        model = RoomAttributeAssignment
        fields = ["id", "attribute", "slug", "name", "icon", "is_active", "note"]
        read_only_fields = ["id"]


class RoomSerializer(serializers.ModelSerializer[Room]):
    """Room with inline bed config and amenity links.

    `beds` upserts; `attribute_links` is a full-list sync (absent on PATCH =
    leave links alone). A non-blank `ensuite_type` refines `is_ensuite` to
    True ("refines" semantics, GAP-064); a blank one never touches the bool.
    """

    beds = _RoomBedsSerializer(required=False)
    attribute_links = _RoomAttributeLinkSerializer(many=True, required=False)

    class Meta:
        model = Room
        fields = [
            "id",
            "property",
            "name",
            "placement",
            "floor",
            "placement_note",
            "website_description",
            "vc_notes",
            "is_ensuite",
            "ensuite_type",
            "access",
            "sort_order",
            "beds",
            "attribute_links",
        ]
        read_only_fields = ["id", "property"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Coherence (mirrors the DB CheckConstraint): a typed ensuite is
        # ensuite, and unticking the ensuite flag clears any (possibly stale
        # instance-side) type — otherwise the constraint would 500 the PATCH.
        if attrs.get("ensuite_type"):
            attrs["is_ensuite"] = True
        elif attrs.get("is_ensuite") is False:
            attrs["ensuite_type"] = ""
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Room:
        beds_data = validated_data.pop("beds", None)
        links = validated_data.pop("attribute_links", None)
        with transaction.atomic():
            room = Room.objects.create(**validated_data)
            RoomBeds.objects.create(room=room, **(beds_data or {}))
            if links:
                self._sync_attribute_links(room, links)
        return room

    def update(self, instance: Room, validated_data: dict[str, Any]) -> Room:
        beds_data = validated_data.pop("beds", None)
        # Absent on a partial PATCH → leave the existing links alone.
        has_links = "attribute_links" in validated_data
        links = validated_data.pop("attribute_links", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if beds_data is not None:
            RoomBeds.objects.update_or_create(room=instance, defaults=beds_data)
        if has_links:
            self._sync_attribute_links(instance, links or [])
        return instance

    @staticmethod
    def _sync_attribute_links(instance: Room, links: list[dict[str, Any]]) -> None:
        """Diff the room's amenity links against the desired full list.
        Per-row `create`/`delete`/`save` (never `bulk_*`) so each change fires
        its audit signal (FG-017). Duplicate attribute ids collapse to their
        first entry (the unique constraint forbids repeats). Links to retired
        attributes resubmitted by the form are kept, never 400d (B1)."""
        desired: dict[int, str] = {}
        for link in links:
            attribute = link["attribute"]
            if attribute.pk not in desired:
                desired[attribute.pk] = link.get("note", "")
        with transaction.atomic():
            existing = {link.attribute_id: link for link in instance.attribute_links.all()}
            for attribute_id, link_obj in existing.items():
                if attribute_id not in desired:
                    link_obj.delete()
            for attribute_id, note in desired.items():
                existing_link = existing.get(attribute_id)
                if existing_link is None:
                    RoomAttributeAssignment.objects.create(
                        room=instance, attribute_id=attribute_id, note=note
                    )
                elif existing_link.note != note:
                    existing_link.note = note
                    existing_link.save(update_fields=["note"])
