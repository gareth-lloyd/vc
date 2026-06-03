from __future__ import annotations

from django.apps import AppConfig


class OwnersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "owners"

    def ready(self) -> None:
        from core.audit import track
        from owners.models import OwnerMembership, OwnerOrganisation, OwnerOrgProperty

        # Org lifecycle + tax/billing identity are operationally sensitive.
        track(
            OwnerOrganisation,
            fields=["name", "tax_number", "billing_address", "status"],
        )
        # Who may log in for which org, in what role — an authz-shaping change.
        # Track the FK *_id scalars (JSON-serialisable), never the FK objects:
        # AuditLog.field_diffs is encoded with DjangoJSONEncoder, which can't
        # serialise a model instance.
        track(
            OwnerMembership,
            fields=["organisation_id", "user_id", "role", "status", "invited_by_id", "accepted_at"],
        )
        # The visibility grant flags decide what an owner can see; every flip
        # must leave an audit trail.
        track(
            OwnerOrgProperty,
            fields=[
                "organisation_id",
                "property_id",
                "view_full_money",
                "view_guest_details",
                "end_date",
            ],
        )
