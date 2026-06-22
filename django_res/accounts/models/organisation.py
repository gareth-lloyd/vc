from __future__ import annotations

from django.db import models, transaction

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

        Generic ``_meta.related_objects`` walk: the sole inbound FK today is
        ``Person.agency`` — a plain nullable FK with no FK-scoped unique
        constraints — so a bare bulk ``.update()`` is safe. Unlike
        ``Person.merge`` there are no channel children to reconcile and no
        ``one_primary_*`` partials to trip. PROTECT on ``Person.agency`` would
        block a naive ``delete()`` while agents remain, so the rewrite must run
        first.

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
            count = related_model._default_manager.filter(**{field_name: self}).update(
                **{field_name: target}
            )
            if count:
                rewrites[f"{related_model._meta.label}.{field_name}"] = count
        dead_pk = self.pk
        target_pk = target.pk
        self.delete()
        self.pk = dead_pk
        record_merge(self, target_pk, rewrites)
