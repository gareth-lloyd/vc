"""PersonRelationship — durable person-to-person links (GAP-041).

A directed row `(from_person, to_person, kind)` that reads "*to_person* is
*from_person*'s *{kind}*" (e.g. spouse / child / PA). Distinct from the
per-booking `reservations.BookingGuest` trip roles: these stand across bookings
so the sales team has the full relationship picture when quoting.

One directed row is the single source of truth — the reverse side renders an
inverse label (`accounts.enums.RELATIONSHIP_INVERSE_LABEL`) rather than a mirror
row, so there is never a second row to keep in sync.
"""

from __future__ import annotations

from django.db import models
from django.db.models import F, Q

from accounts.enums import PersonRelationshipKind
from core.models.base import AuditedModel


class PersonRelationship(AuditedModel):
    """A standing link between two Persons under one relationship kind."""

    from_person = models.ForeignKey(
        "accounts.Person",
        on_delete=models.CASCADE,
        related_name="relationships_out",
    )
    to_person = models.ForeignKey(
        "accounts.Person",
        on_delete=models.CASCADE,
        related_name="relationships_in",
    )
    kind = models.CharField(max_length=16, choices=PersonRelationshipKind.choices)
    note = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_person", "to_person", "kind"],
                name="personrelationship_unique_from_to_kind",
            ),
            # A person can't be linked to themselves. Enforced at the DB so a
            # merge that would repoint a row into a self-link must drop it
            # (handled in Person._merge_relationships), never persist it.
            models.CheckConstraint(
                condition=~Q(from_person=F("to_person")),
                name="personrelationship_no_self_link",
            ),
        ]
        indexes = [
            models.Index(fields=["from_person", "kind"]),
            models.Index(fields=["to_person", "kind"]),
        ]
        ordering = ["from_person_id", "id"]

    def __str__(self) -> str:
        return f"PersonRelationship #{self.pk} ({self.kind})"


__all__ = ["PersonRelationship"]
