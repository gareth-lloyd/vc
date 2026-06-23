"""Serializer for the `/contacts/{id}/relationships` sub-resource (GAP-041).

Projects a single directed `PersonRelationship` row *relative to the profile
being viewed* (`context["viewed_person_id"]`): the read shape always shows the
**other** party and the kind **as seen from this profile** — an incoming row
gets its inverse label (a CHILD row read from the parent's profile shows
"Parent"). Writes create an outgoing row from the viewed profile.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from accounts.enums import (
    RELATIONSHIP_INVERSE_KIND,
    RELATIONSHIP_INVERSE_LABEL,
    PersonRelationshipKind,
    PersonStatus,
)
from accounts.models import Person, PersonRelationship


class LinkedContactSerializer(serializers.ModelSerializer[PersonRelationship]):
    """One linked contact, oriented to `context["viewed_person_id"]`."""

    # Write: the other party + the stored kind ("{to_person} is {viewed}'s
    # {kind}"). `from_person` is taken from the URL in the viewset, never the body.
    # ANONYMIZED persons are excluded — you can't form a fresh standing link to a
    # GDPR-erased contact (and anonymize() drops existing links anyway).
    to_person = serializers.PrimaryKeyRelatedField(
        queryset=Person.objects.exclude(status=PersonStatus.ANONYMIZED), write_only=True
    )
    # Read projections.
    other_person = serializers.SerializerMethodField()
    kind_label = serializers.SerializerMethodField()
    direction = serializers.SerializerMethodField()

    class Meta:
        model = PersonRelationship
        fields = [
            "id",
            "to_person",
            "kind",
            "kind_label",
            "note",
            "other_person",
            "direction",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def _viewed_id(self) -> int:
        return int(self.context["viewed_person_id"])

    def _is_outgoing(self, obj: PersonRelationship) -> bool:
        return obj.from_person_id == self._viewed_id()

    def get_other_person(self, obj: PersonRelationship) -> dict[str, Any]:
        other = obj.to_person if self._is_outgoing(obj) else obj.from_person
        return {
            "id": other.pk,
            "first_name": other.first_name,
            "last_name": other.last_name,
            "display_name": other.display_name,
            "kind": other.kind,
        }

    def get_kind_label(self, obj: PersonRelationship) -> str:
        # Outgoing: the stored kind describes the other party directly. Incoming:
        # render the inverse ("X is Y's CHILD" → on Y's profile X is the "Parent").
        if self._is_outgoing(obj):
            return str(PersonRelationshipKind(obj.kind).label)
        return RELATIONSHIP_INVERSE_LABEL[obj.kind]

    def get_direction(self, obj: PersonRelationship) -> str:
        return "outgoing" if self._is_outgoing(obj) else "incoming"

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        viewed_id = self._viewed_id()
        to_person = attrs["to_person"]
        if to_person.pk == viewed_id:
            raise serializers.ValidationError(
                {"to_person": "A contact cannot be linked to themselves."}
            )
        kind = attrs["kind"]
        if PersonRelationship.objects.filter(
            from_person_id=viewed_id, to_person=to_person, kind=kind
        ).exists():
            raise serializers.ValidationError("This relationship already exists.")
        # Reject the mirror row too: "(Alice, Bob, SPOUSE)" and "(Bob, Alice,
        # SPOUSE)" are one fact, as are "(Alice, Bob, CHILD)" and "(Bob, Alice,
        # PARENT)". The single directed row is the source of truth (the reverse
        # profile renders an inverse label), so block recording it twice. PA has
        # no storable inverse, so a reverse PA is a genuinely distinct link.
        inverse_kind = RELATIONSHIP_INVERSE_KIND.get(kind)
        if (
            inverse_kind is not None
            and PersonRelationship.objects.filter(
                from_person=to_person, to_person_id=viewed_id, kind=inverse_kind
            ).exists()
        ):
            raise serializers.ValidationError(
                "This relationship already exists (recorded from the other contact)."
            )
        return attrs
