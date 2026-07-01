from __future__ import annotations

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self) -> None:
        from accounts import signals  # noqa: F401
        from accounts.models import (
            Organisation,
            Person,
            PersonRelationship,
            User,
        )
        from core.audit import track

        track(
            Person,
            fields=[
                "title",
                "first_name",
                "last_name",
                "address_line_1",
                "address_line_2",
                "town",
                "post_code",
                # GAP-052: country is now operator-editable → audited. FK by its
                # `_id` attname so the diff stores the pk, not a Country instance
                # (per the PersonRelationship convention). A public FK, not PII,
                # so it stays out of `_AUDIT_PII_FIELDS`/`anonymize()`.
                "country_id",
                "marketing_consent",
                "notes",
                "status",
                "kind",
                "tags",
            ],
        )
        # User auth/role/2FA changes — record what shifted, never the
        # cleartext secret. Password rotations are caught by Django's own
        # auth machinery; we deliberately skip the hash here.
        track(
            User,
            fields=[
                "email",
                "phone",
                "role",
                "is_active",
                "is_staff",
                "is_superuser",
                "tfa_method",
                "tfa_secret",
                "tfa_enrolled_at",
                "last_login_ip",
                "preferred_language",
            ],
            sensitive=["tfa_secret"],
        )
        # GAP-041: standing person-to-person links. Tracked so add/remove/retype
        # of a relationship is in the trail; bulk merge rewrites go per-instance
        # (Person._merge_relationships) so they hit these signals.
        #
        # `note` is deliberately NOT tracked: it's operator free-text that may
        # carry special-category PII, and on erasure the row is hard-deleted —
        # the post_delete audit row then lives under the PersonRelationship
        # content-type, which Person.scrub_pii (keyed on the Person content-type)
        # can't reach. Auditing the parties + kind captures the link's meaning;
        # the free-text gloss stays out of an unscrubportable trail.
        track(
            PersonRelationship,
            # FK columns by their `_id` attname (per the payments/owners
            # convention) so the diff records the pk, not an unserializable
            # Person instance.
            fields=["from_person_id", "to_person_id", "kind"],
        )
        # Organisation carries contact detail (email/phone/address) → audited.
        # No `sensitive` fields and no erasure scrub: an organisation is not a
        # GDPR data subject (GAP-046).
        track(
            Organisation,
            fields=[
                "name",
                "org_type",
                "email",
                "phone",
                "address_line_1",
                "address_line_2",
                "town",
                "post_code",
                "website_url",
                "notes",
                "status",
            ],
        )
