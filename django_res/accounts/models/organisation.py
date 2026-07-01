from __future__ import annotations

from django.db import models, transaction
from django.db.models import Q

from accounts.enums import OrgStatus, OrgType
from core.audit import record_merge
from core.fields import CIEmailField
from core.models.base import AuditedModel


class Organisation(AuditedModel):
    """A business entity: a travel agency, a property-management company, or a
    concierge supplier (partitioned by ``org_type``). GAP-046.

    Distinct from ``owners.OwnerOrganisation`` — that models a *supply-side*
    owner-portal tenant (a login boundary for owners). This is a directory
    record on the operator's side: the thing a ``Person.agency`` points at, the
    rows behind the B2B "Companies" screen. Different label, different table.
    """

    name = models.CharField(max_length=128)
    org_type = models.CharField(
        max_length=16,
        choices=OrgType.choices,
        default=OrgType.AGENCY,
    )
    email = CIEmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
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
    website_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=OrgStatus.choices,
        default=OrgStatus.ACTIVE,
    )
    # Synthesised idempotency key for the company-string → Organisation backfill
    # (a content-hash of the normalised name): get_or_create(dedup_key=…) so a
    # re-run converges and distinct names never collide. Kept OFF `legacy_id`
    # because CLAUDE.md reserves legacy_id for real legacy-origin IDs ("never the
    # application lookup key") — backfilled orgs have no source ID. unique +
    # null=True is partial-unique on Postgres (NULLs distinct), so API/FE-created
    # orgs leave it NULL and never collide.
    dedup_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    # Plain migration metadata for orgs with a genuine legacy origin (e.g. future
    # supplier imports); NULL for company-string backfills. Per CLAUDE.md, never
    # the application lookup key.
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "name"]),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @transaction.atomic
    def merge(self, target: Organisation) -> None:
        """Repoint every FK pointing at ``self`` onto ``target``, then hard-delete
        ``self``. The AuditLog deletion row is the only trail.

        Generic ``_meta.related_objects`` walk. Most inbound FKs (e.g.
        ``Person.agency``) are plain nullable FKs with no FK-scoped unique
        constraint, so a bare bulk ``.update()`` is safe. The exception is
        ``PropertyContactAssignment.organisation``, whose partial unique
        ``(property, organisation, role) WHERE end_date IS NULL`` would raise an
        ``IntegrityError`` if both orgs hold an open assignment on the same
        ``(property, role)`` — so that relation is deduped via
        ``_merge_related`` (drop the colliding source row). PROTECT on the
        inbound FKs would block a naive ``delete()`` while rows remain, so the
        rewrite must run first.

        An Organisation is not a GDPR data subject (no ANONYMIZED status), so we
        ``record_merge`` for the trail but never ``scrub_pii``.
        """
        if target.pk == self.pk:
            raise ValueError("Cannot merge an organisation into itself")
        # The .update() rewrites bypass the audit signals, so summarise what
        # moved (per-relation counts) onto the deletion row (mirrors FG-016).
        rewrites: dict[str, int] = {}
        for rel in self._meta.related_objects:
            related_model = rel.related_model
            if related_model is None or isinstance(related_model, str):
                continue
            # M2M reverse relations surface separately as their through model's
            # FK; .update() on the virtual M2M field raises FieldError.
            if rel.many_to_many:
                continue
            field_name = rel.field.name
            count = self._merge_related(target, related_model, field_name)
            if count:
                rewrites[f"{related_model._meta.label}.{field_name}"] = count
        dead_pk = self.pk
        target_pk = target.pk
        self.delete()
        self.pk = dead_pk
        record_merge(self, target_pk, rewrites)

    def _merge_related(
        self, target: Organisation, model: type[models.Model], field_name: str
    ) -> int:
        """Move ``self``'s rows of ``model`` (linked via ``field_name``) onto
        ``target``, dropping any source row that would collide with an existing
        target row under one of ``model``'s FK-involving unique constraints.

        Mirrors ``Person._merge_relation`` but reads ``model._meta.constraints``
        directly rather than ``total_unique_constraints`` — the latter EXCLUDES
        conditional/partial constraints, and the only relation that needs the
        dedupe here (``PropertyContactAssignment.organisation``) is scoped by a
        ``WHERE end_date IS NULL`` partial unique. Each constraint's
        ``.condition`` is applied via the ORM on BOTH the target-signature query
        and the source rows, so only rows the partial actually constrains are
        deduped. Relations with no FK-involving unique constraint short-circuit
        to a bare bulk ``.update()``.

        Model-agnostic: no ``properties`` import (``accounts`` is the bottom of
        the import spine) — ``rel.related_model`` hands us the class at runtime.
        """
        constraints = [
            c
            for c in model._meta.constraints
            if isinstance(c, models.UniqueConstraint) and field_name in c.fields
        ]
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
            condition = constraint.condition or Q()
            others = [f for f in constraint.fields if f != field_name]
            other_attnames = [
                model._meta.get_field(f).attname  # type: ignore[union-attr]
                for f in others
            ]
            existing = set(
                model._default_manager.filter(condition, **{field_name: target}).values_list(
                    *others
                )
            )
            # Only source rows the partial condition actually constrains can
            # collide — a closed (end_date set) source row is outside the
            # partial and moves freely.
            constrained_pks = set(
                model._default_manager.filter(condition, **{field_name: self}).values_list(
                    "pk", flat=True
                )
            )
            for row in source_rows:
                if row.pk not in constrained_pks:
                    continue
                signature = tuple(getattr(row, attname) for attname in other_attnames)
                if signature in existing:
                    colliding.add(row.pk)

        # Per-instance delete (not bulk) so a tracked model leaves an audit
        # trail — bulk deletes fire no post_delete signal (django_res/CLAUDE.md).
        for row in source_rows:
            if row.pk in colliding:
                row.delete()
        moved_pks = [row.pk for row in source_rows if row.pk not in colliding]
        if not moved_pks:
            return 0
        return model._default_manager.filter(pk__in=moved_pks).update(**{field_name: target})
