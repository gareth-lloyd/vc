from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from accounts.enums import (
    RELATIONSHIP_INVERSE_KIND,
    EmailLabel,
    PersonKind,
    PersonPreferredMethod,
    PersonStatus,
    PersonTag,
    PhoneLabel,
)
from core.audit import record_merge, scrub_pii
from core.fields import CIEmailField
from core.models.base import AuditedModel, TimestampedModel


class Person(AuditedModel):
    """Villa owner, property manager, or external agent.

    Distinct from `User` because most people never log in. If they do,
    we link via the optional `user` OneToOne.
    """

    title = models.CharField(max_length=16, blank=True)
    # GAP-029: names are optional — an agency/company-only contact carries no
    # personal name. The "at least a name OR an agency" floor is enforced in
    # `ContactSerializer.validate()` (app-level, mirroring the channel-
    # contactability gate), not a DB CHECK.
    first_name = models.CharField(max_length=128, blank=True)
    last_name = models.CharField(max_length=128, blank=True)
    # GAP-046: structured agency link — the successor to the free-text `company`
    # field, which was dropped once every read was switched to `agency`/
    # `agency_name` (migration 0012). "Is an agent" stays derived (has an agency /
    # referenced as an `.agent`) — no capacity column (GAP-045 rule). PROTECT: an
    # Organisation with agents can't be deleted out from under them (merge
    # repoints first).
    agency = models.ForeignKey(
        "accounts.Organisation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="agents",
    )
    website_url = models.URLField(blank=True)
    preferred_method = models.CharField(
        max_length=8,
        choices=PersonPreferredMethod.choices,
        default=PersonPreferredMethod.EMAIL,
    )
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    town = models.CharField(max_length=128, blank=True)
    post_code = models.CharField(max_length=32, blank=True)
    country = models.ForeignKey(
        "properties.Country",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    marketing_consent = models.BooleanField(default=False)
    # GAP-040: operator-applied flags (VIP / Trade / Disability / …). A fixed
    # `PersonTag` taxonomy stored as a Postgres array — queryable (`tags__overlap`)
    # and audited as a whole-set replace. `save()` normalizes to a sorted,
    # de-duplicated list so the same set in any order is one canonical value (no
    # spurious audit row on a checkbox reorder). Membership validation lives in
    # the serializer (ChoiceField), not a DB constraint, mirroring `kind`/`status`.
    tags = ArrayField(
        models.CharField(max_length=32, choices=PersonTag.choices),
        default=list,
        blank=True,
    )
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=PersonStatus.choices,
        default=PersonStatus.ACTIVE,
    )
    # GAP-045 D2: directory classification (CUSTOMER vs business CONTACT). Set to
    # CUSTOMER by the Guest→Person sync + customer-create path; defaults CONTACT
    # for owner/agent records. A `/contacts` filter hint, not access control.
    kind = models.CharField(
        max_length=16,
        choices=PersonKind.choices,
        default=PersonKind.CONTACT,
    )
    anonymized_at = models.DateTimeField(null=True, blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contact",
    )
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    # Audit-tracked columns carrying cleartext PII. Erasure flows scrub these
    # from the AuditLog trail (BUG-012); non-PII tracked columns (status) stay.
    _AUDIT_PII_FIELDS = (
        "title",
        "first_name",
        "last_name",
        "address_line_1",
        "address_line_2",
        "town",
        "post_code",
        "notes",
    )

    class Meta:
        indexes = [
            models.Index(fields=["status", "last_name", "first_name"]),
        ]
        ordering = ["last_name", "first_name"]

    def save(self, *args: Any, **kwargs: Any) -> None:
        # GAP-040: canonicalize tags to a sorted, de-duplicated list. The audit
        # diff is order-sensitive (core/audit.py compares old != new by value), so
        # normalizing here makes a reorder a no-op write on every path — serializer,
        # seed_dev, data-migration loaders, shell — not just the serializer.
        if self.tags:
            self.tags = sorted(set(self.tags))
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        if self.status == PersonStatus.ANONYMIZED:
            return f"[redacted person #{self.pk}]"
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self) -> str | None:
        """Full name for staff lists, or ``None`` when both name parts blank."""
        return f"{self.first_name} {self.last_name}".strip() or None

    @property
    def agency_name(self) -> str:
        """Display name of the linked agency, or ``""`` when unlinked (GAP-046).

        The structured successor to the free-text ``company`` (dropped in the
        contract step): readers that fell back to ``company`` now read this.
        A null FK returns ``""`` without firing a query (the descriptor yields
        ``None`` for an unset ``agency_id``); the live read paths select_related
        ``agency`` so the linked case is cache-hit too. Callers wanting an
        Optional treat ``""`` as falsy (``agency_name or None``).
        """
        agency = self.agency
        return agency.name if agency is not None else ""

    def primary_email(self) -> str | None:
        """Primary email address, read from the prefetch cache.

        Iterates ``self.emails.all()`` (so it stays inside a
        ``prefetch_related("emails")`` budget rather than firing a fresh
        ``.filter()`` per row). Returns the ``is_primary`` address, else the
        oldest by pk — matching ``comms.recipients._primary_contact_email``.
        Guest mirrors always carry exactly one PRIMARY (GAP-045 Unit 3c-1a),
        so the oldest-by-pk fallback only matters for non-mirror Persons.

        Fails closed for an ANONYMIZED Person: ``Person.anonymize`` rewrites
        each PersonEmail to a syntactically-valid ``redacted-…@anonymized.local``
        sentinel and keeps the row, so without this guard a person-first read
        (staff list or comms send) would surface — and mail — that sentinel.
        Returning ``None`` here is the single chokepoint that protects both.
        """
        if self.status == PersonStatus.ANONYMIZED:
            return None
        emails = list(self.emails.all())
        if not emails:
            return None
        for email in emails:
            if email.is_primary:
                return email.email
        return min(emails, key=lambda e: e.pk).email

    def primary_phone(self) -> str | None:
        """Primary phone number from the prefetch cache (see ``primary_email``).

        Fails closed for an ANONYMIZED Person, mirroring ``primary_email``.
        """
        if self.status == PersonStatus.ANONYMIZED:
            return None
        phones = list(self.phones.all())
        if not phones:
            return None
        for phone in phones:
            if phone.is_primary:
                return phone.number or None
        return min(phones, key=lambda p: p.pk).number or None

    @transaction.atomic
    def anonymize(self) -> None:
        """Overwrite PII with sentinels and flip status.

        Row is preserved for FK integrity on historical bookings.
        Email/phone children are anonymized in lockstep.
        """
        self.first_name = "[REDACTED]"
        self.last_name = "[REDACTED]"
        self.notes = ""
        self.address_line_1 = ""
        self.address_line_2 = ""
        self.town = ""
        self.post_code = ""
        # GAP-040: tags can carry special-category data (Disability /
        # Approach-with-care) — drop them from the live record on erasure, and
        # scrub them from the audit trail below (else "disability was added" stays
        # recoverable). In normal operation tags are kept in clear (auditable);
        # only a true erasure redacts them.
        self.tags = []
        self.status = PersonStatus.ANONYMIZED
        self.anonymized_at = timezone.now()
        self.save(
            update_fields=[
                "first_name",
                "last_name",
                "notes",
                "address_line_1",
                "address_line_2",
                "town",
                "post_code",
                "tags",
                "status",
                "anonymized_at",
                "updated_at",
            ]
        )
        for email in self.emails.all():
            email.email = f"redacted-{email.pk}@anonymized.local"
            email.save(update_fields=["email", "updated_at"])
        for phone in self.phones.all():
            phone.number = ""
            phone.save(update_fields=["number", "updated_at"])
        # GAP-041: drop standing relationships on erasure — a surviving link
        # leaks "X is [redacted]'s spouse". Per-instance delete keeps the
        # PersonRelationship audit trail. Lazy import: person_relationship imports
        # Person, so a module-level import here would cycle.
        from accounts.models.person_relationship import PersonRelationship

        for rel in PersonRelationship._default_manager.filter(
            Q(from_person=self) | Q(to_person=self)
        ):
            rel.delete()
        # Scrub *after* the save so the freshly written [old, sentinel] row is
        # caught alongside the historical trail (BUG-012). `tags` rides along
        # (special-category data, GAP-040) even though it's absent from
        # `_AUDIT_PII_FIELDS` — that tuple gates merge's scrub, where tags are not
        # erased, only here on a true erasure.
        scrub_pii(self, (*self._AUDIT_PII_FIELDS, "tags"))

    @transaction.atomic
    def merge(self, target: Person) -> None:
        """Rewrite FKs pointing at `self` to point at `target`, then hard-delete self.

        Destructive: there is no merged_into back-reference. The AuditLog is
        the only trail.
        """
        if target.pk == self.pk:
            raise ValueError("Cannot merge a person into itself")
        from accounts.models.person_relationship import PersonRelationship

        # Apps that hold FKs to Person are properties.PropertyContactAssignment,
        # reservations.Enquiry/Quotation/Booking (agent FKs),
        # properties.PropertyFinance.contact. Their migrations create the
        # reverse relations; we rewrite via _meta.related_objects so the merge
        # works without hard-coding which apps exist yet.
        # The .update() rewrites bypass the audit signals, so record a summary
        # of what moved (per-relation counts) onto the deletion row (FG-016).
        # The channel children carry partial-unique constraints
        # (one_primary_*_per_contact + unique_contact_email/number), so a blind
        # `.update(contact=target)` collides whenever both Persons own a primary
        # or share an address. Reconcile them explicitly instead.
        channel_value_fields: dict[type[models.Model], str] = {
            PersonEmail: "email",
            PersonPhone: "number",
        }
        rewrites: dict[str, int] = {}
        for rel in self._meta.related_objects:
            related_model = rel.related_model
            if related_model is None or isinstance(related_model, str):
                continue
            # Skip M2M reverse relations: the through model shows up separately
            # as its own FK relation and is rewritten there. .update() on an
            # M2M field raises FieldError because it isn't a column.
            if rel.many_to_many:
                continue
            # PersonRelationship surfaces TWICE here (its from_person + to_person
            # FKs both point at Person), and a blind per-FK rewrite would repoint
            # a link between the two merged people into a self-link (tripping the
            # CheckConstraint) or a duplicate. Fold both legs once, below.
            if related_model is PersonRelationship:
                continue
            field_name = rel.field.name
            value_field = channel_value_fields.get(related_model)
            if value_field is not None:
                count = self._merge_channel(target, related_model, value_field)
            else:
                count = self._merge_relation(target, related_model, field_name)
            if count:
                rewrites[f"{related_model._meta.label}.{field_name}"] = count
        # One-shot relationship fold (both FK legs), after the generic loop.
        rel_label = PersonRelationship._meta.label
        for leg, count in self._merge_relationships(target).items():
            if count:
                rewrites[f"{rel_label}.{leg}"] = count
        dead_pk = self.pk
        target_pk = target.pk
        self.delete()
        # Scrub by the now-dead pk so the deletion row's [old_PII, None] pairs
        # are redacted while __deleted__/actor/timestamps survive (BUG-012).
        self.pk = dead_pk
        # Stamp merge summary onto the deletion row *before* scrubbing so the
        # augmented row is scrubbed too (FG-016).
        record_merge(self, target_pk, rewrites)
        scrub_pii(self, self._AUDIT_PII_FIELDS)

    def _merge_channel(self, target: Person, model: type[models.Model], value_field: str) -> int:
        """Fold ``self``'s email/phone rows into ``target`` without tripping the
        channel constraints. The survivor keeps its own primary; a source row
        whose address already exists on the target is dropped; the rest move in
        as non-primary — unless the target has no primary, in which case the
        source's primary is promoted so the merged Person stays contactable.
        Returns the number of rows actually moved (dropped duplicates excluded).
        """
        target_values = set(
            model._default_manager.filter(contact=target).values_list(value_field, flat=True)
        )
        target_has_primary = model._default_manager.filter(contact=target, is_primary=True).exists()
        moved = 0
        for row in model._default_manager.filter(contact=self):
            if getattr(row, value_field) in target_values:
                row.delete()  # duplicate address — the target already has it
                continue
            row.contact = target  # type: ignore[attr-defined]
            if target_has_primary:
                row.is_primary = False  # type: ignore[attr-defined]
            elif row.is_primary:  # type: ignore[attr-defined]
                target_has_primary = True  # this row becomes the survivor's primary
            row.save(update_fields=["contact", "is_primary", "updated_at"])
            moved += 1
        return moved

    def _merge_relation(self, target: Person, model: type[models.Model], field_name: str) -> int:
        """Move ``self``'s rows of ``model`` (linked via ``field_name``) onto
        ``target``, dropping any source row that would collide with an existing
        target row under one of ``model``'s FK-involving unique constraints.

        Most relations have no such constraint and short-circuit to a bare bulk
        ``.update()`` — identical to the pre-GAP-045 behaviour. Only models that
        scope a unique constraint by this FK (``BookingGuest`` on
        ``(booking, person, role)``, ``GuestPreference`` on
        ``(person, preference_type, quotation)``) need the dedupe: a blind update
        would either raise ``IntegrityError`` or — for the nullable ``quotation``
        leg, whose NULLs the DB constraint treats as distinct — silently
        duplicate. The Python ``None``-equality membership test below is stricter
        than the constraint and so dedupes those too. Returns the number of rows
        actually moved (dropped duplicates excluded). Model-agnostic — no
        reservations import (``accounts`` is the bottom of the import spine).
        """
        # total_unique_constraints excludes conditional/expression constraints
        # (so the channel partials and one_lead/one_payer partials never reach
        # here) and covers only Meta UniqueConstraints — not unique_together or
        # Field(unique=True), neither of which any Person-related model uses.
        constraints = [c for c in model._meta.total_unique_constraints if field_name in c.fields]
        if not constraints:
            return model._default_manager.filter(**{field_name: self}).update(
                **{field_name: target}
            )

        # MUST be DB-loaded: getattr on an in-memory row would return enum
        # members for TextChoices fields (e.g. role), which would not match the
        # plain scalars values_list yields below.
        source_rows = list(model._default_manager.filter(**{field_name: self}))
        if not source_rows:
            return 0

        colliding: set[int] = set()
        for constraint in constraints:
            others = [f for f in constraint.fields if f != field_name]
            # Constraint fields are always concrete fields, so .attname holds the
            # FK ``_id`` column matching the values_list pks below (ForeignObjectRel
            # has no attname — hence the ignore). Resolved once per constraint.
            other_attnames = [
                model._meta.get_field(f).attname  # type: ignore[union-attr]
                for f in others
            ]
            # values_list yields the FK pk (None for NULL) per field, so a
            # NULL-vs-NULL pair matches here even though the DB constraint would
            # treat them as distinct — this is the dup-NULL fix.
            existing = set(
                model._default_manager.filter(**{field_name: target}).values_list(*others)
            )
            for row in source_rows:
                signature = tuple(getattr(row, attname) for attname in other_attnames)
                if signature in existing:
                    colliding.add(row.pk)

        # Drop colliding source rows one at a time, not via a bulk
        # ``queryset.delete()``: a colliding row of a *tracked* model (e.g.
        # BookingGuest) must leave an audit trail, and bulk deletes fire no
        # post_delete signal (django_res/CLAUDE.md). Per-instance delete mirrors
        # ``_merge_channel``. A colliding row is never a LEAD BookingGuest (two
        # LEADs can't share a booking), so the LEAD pre_delete guard never trips.
        for row in source_rows:
            if row.pk in colliding:
                row.delete()
        moved_pks = [row.pk for row in source_rows if row.pk not in colliding]
        if not moved_pks:
            return 0
        return model._default_manager.filter(pk__in=moved_pks).update(**{field_name: target})

    def _merge_relationships(self, target: Person) -> dict[str, int]:
        """Fold ``self``'s PersonRelationship rows onto ``target`` across both FK
        legs without tripping the no-self-link CheckConstraint or the
        ``(from, to, kind)`` UniqueConstraint.

        Called once from ``merge`` (PersonRelationship is skipped in the generic
        ``related_objects`` loop, where it would otherwise surface twice and
        double-rewrite). For each row, compute its post-repoint ``(from, to,
        kind)`` and:

        - **drop** it (per-instance ``.delete()``) if that collapses to a
          self-link (the two merged people were linked to each other) or
          duplicates a relationship the target already has;
        - otherwise **repoint** the leg(s) that pointed at ``self`` via
          per-instance ``.save()``.

        Per-instance writes (never bulk ``.update()``/``.delete()``) keep the
        tracked audit trail intact, mirroring ``_merge_channel``. Returns moved
        counts keyed by leg (``from_person`` / ``to_person``) for the merge
        summary.
        """
        from accounts.models.person_relationship import PersonRelationship

        moved = {"from_person": 0, "to_person": 0}
        # Signatures already on the target (either leg) to dedup against; a row
        # could only be on one leg of self (the constraint forbids from == to).
        existing = {
            (r.from_person_id, r.to_person_id, r.kind)
            for r in PersonRelationship._default_manager.filter(
                Q(from_person=target) | Q(to_person=target)
            )
        }
        for row in PersonRelationship._default_manager.filter(
            Q(from_person=self) | Q(to_person=self)
        ):
            leg = "from_person" if row.from_person_id == self.pk else "to_person"
            new_from = target.pk if row.from_person_id == self.pk else row.from_person_id
            new_to = target.pk if row.to_person_id == self.pk else row.to_person_id
            if new_from == new_to:
                row.delete()  # the two merged people were linked → self-link
                continue
            signature = (new_from, new_to, row.kind)
            # A mirror of an existing target row is the same fact (the merge can
            # turn (Carol, dup, SPOUSE) into (Carol, keep, SPOUSE) while the
            # target already holds (keep, Carol, SPOUSE)). Drop it so the merge
            # upholds the single-source-of-truth invariant, not just the DB
            # constraint. PA has no storable inverse → never a mirror.
            inverse_kind = RELATIONSHIP_INVERSE_KIND.get(row.kind)
            mirror = (new_to, new_from, inverse_kind) if inverse_kind is not None else None
            if signature in existing or (mirror is not None and mirror in existing):
                row.delete()  # target already has this relationship (either way round)
                continue
            existing.add(signature)
            row.from_person_id = new_from
            row.to_person_id = new_to
            row.save(update_fields=["from_person", "to_person", "updated_at"])
            moved[leg] += 1
        return moved


class PersonEmail(TimestampedModel):
    contact = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="emails")
    email = CIEmailField()
    label = models.CharField(max_length=16, choices=EmailLabel.choices, default=EmailLabel.PRIMARY)
    is_primary = models.BooleanField(default=False)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contact", "email"],
                name="unique_contact_email",
            ),
            models.UniqueConstraint(
                fields=["contact"],
                condition=Q(is_primary=True),
                name="one_primary_email_per_contact",
            ),
        ]


class PersonPhone(TimestampedModel):
    contact = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="phones")
    number = models.CharField(max_length=32)
    label = models.CharField(max_length=16, choices=PhoneLabel.choices, default=PhoneLabel.MOBILE)
    is_primary = models.BooleanField(default=False)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contact", "number"],
                name="unique_contact_phone",
            ),
            models.UniqueConstraint(
                fields=["contact"],
                condition=Q(is_primary=True),
                name="one_primary_phone_per_contact",
            ),
        ]
