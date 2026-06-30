from __future__ import annotations

from django.apps import AppConfig


class PropertiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "properties"

    def ready(self) -> None:
        from core import audit
        from properties import signals  # noqa: F401
        from properties.models.calendar_feed import PropertyCalendarFeed
        from properties.models.changeover import ChangeOverRule
        from properties.models.contacts import PropertyContactAssignment
        from properties.models.features import PropertyFeature
        from properties.models.finance import GroupFinance, PropertyFinance
        from properties.models.geo import PropertyNearbyPlace
        from properties.models.images import PropertyImage
        from properties.models.property import Property
        from properties.models.rooms import Room
        from properties.models.services import PropertyService

        audit.track(
            PropertyCalendarFeed,
            fields=("property_id", "url", "platform", "label", "is_active"),
            sensitive=("url",),
        )

        _SENSITIVE_BANK_FIELDS = (
            "bank_account_number",
            "bank_iban",
            "bank_bic",
            "bank_sort_code",
        )
        _AUDITED_FINANCE_FIELDS = (
            "commission_calculation_type",
            "commission_amount",
            "commission_note",
            "tax_number",
            "tax_is_exempt",
            "tax_percentage",
            "bank_account_name",
            "bank_account_number",
            "bank_sort_code",
            "bank_iban",
            "bank_bic",
            "bank_name",
            "bank_address_line_1",
            "bank_address_line_2",
            "bank_post_code",
            "bank_city",
            "deposit_required",
            "deposit_calculation_type",
            "deposit_amount",
            "interim_required",
            "interim_calculation_type",
            "interim_amount",
            "days_interim_due_before_arrival",
            "days_balance_due_before_arrival",
            "security_deposit_required",
            "security_deposit_calculation_type",
            "security_deposit_amount",
            "security_deposit_days_due_before_arrival",
            "security_deposit_days_refunded_after_departure",
            "security_deposit_payment_method",
            "cancellation_fee_amount",
            "cancellation_fee_percent",
            "cancellation_window_days",
            "cancellation_notes",
        )
        audit.track(
            PropertyFinance,
            fields=_AUDITED_FINANCE_FIELDS,
            sensitive=_SENSITIVE_BANK_FIELDS,
        )
        audit.track(
            GroupFinance,
            fields=_AUDITED_FINANCE_FIELDS,
            sensitive=_SENSITIVE_BANK_FIELDS,
        )

        # Property master record: lifecycle/identity columns only — the chatty
        # description/content fields live on child models and are deliberately
        # excluded (FG-017). Edits to a property's name, status, channel, or its
        # category/group/region placement are the staff actions that leave no
        # trail today.
        audit.track(
            Property,
            fields=(
                "name",
                "display_name",
                "slug",
                "licence_number",
                "status",
                "channel",
                "category_id",
                "group_id",
                "region_id",
            ),
        )

        # Property children: register the few identity fields so a hard delete
        # (via the Destroy views) leaves a `__deleted__` tombstone naming what
        # vanished — the goal of the FG-017 second tier. `track()` gives the
        # post_delete capture for free; the per-edit diffs on these identity
        # fields are a low-noise bonus. None carry denormalised PII (the
        # contact/related identities sit behind FKs).
        audit.track(
            Room,
            fields=("property_id", "name", "placement", "is_ensuite", "sort_order"),
        )
        audit.track(
            PropertyImage,
            fields=("property_id", "kind", "name", "is_active", "sort_order"),
        )
        audit.track(
            PropertyNearbyPlace,
            fields=("property_id", "place_type_id", "name", "distance_km", "sort_order"),
        )
        audit.track(
            ChangeOverRule,
            fields=("property_id", "day", "starts_on", "ends_on"),
        )
        audit.track(
            PropertyContactAssignment,
            fields=(
                "property_id",
                "contact_id",
                "role",
                "start_date",
                "end_date",
                "is_primary",
            ),
        )
        # Deselecting a feature hard-deletes a `PropertyFeature` row, so the link
        # (and its per-villa `sort_order`) must leave a `__deleted__` tombstone
        # naming what vanished (FG-017). Deletes (incl. `.set()`'s removals) and
        # direct `sort_order` edits are captured; additions via the M2M `.set()`
        # go through `bulk_create` and fire no `pre_save`, so granting a feature
        # is not yet logged. That gap closes in GAP-022 step 4, when the write
        # path becomes an explicit per-row diff-writer (add/remove/update) so a
        # reorder logs only the moved rows and an addition logs its own row.
        audit.track(
            PropertyFeature,
            fields=("property_id", "feature_id", "sort_order"),
        )
        # Included services carry guest-facing `copy` and an absolute date band;
        # staff edits (and hard deletes via the Destroy view) need a trail.
        # Track structural fields — the free-text `copy`/`notes` blobs are
        # deliberately excluded as chatty (the FG-017 identity-field pattern).
        audit.track(
            PropertyService,
            fields=(
                "property_id",
                "name",
                "applies_from",
                "applies_to",
                "sort_order",
                "is_active",
            ),
        )
