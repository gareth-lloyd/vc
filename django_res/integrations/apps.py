from __future__ import annotations

from typing import Any

from django.apps import AppConfig
from django.db import models


def _person_channel_changed(
    sender: type[models.Model],
    instance: Any,
    **_: Any,
) -> None:
    """PersonEmail/PersonPhone edits ride nested endpoints without touching
    Person (`accounts/serializers/contact.py`), so a child save/delete must
    bump the parent's Zoho push itself (GAP-081)."""
    from accounts.models import Person
    from integrations.services.zoho_flow import enqueue_zoho_push

    try:
        person = instance.contact
    except Person.DoesNotExist:
        # Cascade delete mid-flight (parent row already gone) — nothing to push.
        return
    enqueue_zoho_push(person)


def _person_relationship_changed(
    sender: type[models.Model],
    instance: Any,
    **_: Any,
) -> None:
    """A PersonRelationship row changes BOTH parties' pushed `relationships`
    list without touching either Person row — bump each leg (GAP-081).
    Per-leg guard: a cascade delete can have removed one party already."""
    from accounts.models import Person
    from integrations.services.zoho_flow import (
        enqueue_zoho_push,
        push_suppressed,
        webhook_url,
    )

    # Guard before the FK derefs: a bulk cascade under suppression (loaders)
    # or with the webhook unset (dev) would otherwise pay 2 SELECTs per row
    # for enqueues that no-op anyway.
    if push_suppressed() or not webhook_url("contact"):
        return
    for field in ("from_person", "to_person"):
        try:
            person = getattr(instance, field)
        except Person.DoesNotExist:
            continue
        enqueue_zoho_push(person)


def _organisation_changed(
    sender: type[models.Model],
    instance: Any,
    **_: Any,
) -> None:
    """Agency fields (incl. `notes`) are embedded in member contacts' payloads,
    so an org edit must re-push its agents as well as itself (GAP-081).

    This is SEPARATE from the org's own `organisation` push (GAP-096): that one
    is the registry's `_post_save_handler`, this one fans out to the embedded
    copies. It retires when the Limitless contact Flow stops reading the
    embedded agency fields and looks the Account up by RES_ID instead
    (CHECK-001) — at which point the embed thins and there is nothing to
    refresh.

    Two known residuals, both deliberate:
    - `Organisation.merge` repoints `Person.agency` via bulk `.update()` (no
      signals), so those members stay stale until their next own bump.
    - Villas are NOT bumped. `properties`' `_organisation_summary` embeds the
      org's name/type/email/phone in every villa payload, but nothing fans out
      Organisation → Property (`properties.signals._VILLA_CHILDREN` reacts to
      `PropertyContactAssignment` saves, not Organisation ones), so a rename
      leaves the old name on managed villas in the CRM until some unrelated
      villa save. Pinned by
      `test_organisation_rename_pushes_once_not_once_per_managed_villa`: the
      fix is the villa Flow looking the Account up by RES_ID (CHECK-003
      item 2), not a fan-out that would cost one villa push per property."""
    from integrations.services.zoho_flow import (
        enqueue_zoho_push,
        push_suppressed,
        webhook_url,
    )

    # Guard before the members query — org saves under suppression (loaders)
    # or with the webhook unset (dev) shouldn't pay it.
    if push_suppressed() or not webhook_url("contact"):
        return
    for person in instance.agents.all():
        enqueue_zoho_push(person)


def _person_merged_receiver(sender: type[models.Model], **kwargs: Any) -> None:
    """`Person.merge` rewrites FKs via `.update()` (no post_save) — re-push the
    survivor so the CRM record absorbs the folded-in channels (GAP-081). The
    absorbed row's CRM record is an accepted orphan (no delete endpoint)."""
    from integrations.services.zoho_flow import enqueue_zoho_push

    enqueue_zoho_push(kwargs["survivor"])


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations"

    def ready(self) -> None:
        from core.audit import track
        from integrations import signals  # noqa: F401
        from integrations.models import OAuthCredential

        # Track sensitive + config-meaningful fields only. Datetime fields
        # (`expires_at`, `disconnected_at`, `connected_at`) are deliberately
        # excluded — the shared `AuditLog.field_diffs` JSONField uses the
        # default JSON encoder, and serialising raw datetimes there would
        # widen `core.audit` semantics. State changes are sufficiently
        # captured via `is_active`.
        track(
            OAuthCredential,
            fields=[
                "provider",
                "account_label",
                "access_token",
                "refresh_token",
                "token_type",
                "scope",
                "account_id",
                "is_active",
            ],
            sensitive=["access_token", "refresh_token"],
        )

        # --- Zoho Flow outbound push (GAP-081) ---------------------------
        from accounts.models import (
            Organisation,
            Person,
            PersonEmail,
            PersonPhone,
            PersonRelationship,
        )
        from accounts.signals import person_merged
        from integrations.services.zoho_flow import register_zoho_flow
        from integrations.services.zoho_payloads import (
            build_organisation_payload,
            build_person_payload,
        )

        register_zoho_flow(Person, kind="contact", build_payload=build_person_payload)
        # GAP-096: the CRM Account's one writer. Lands dark —
        # `ZOHO_FLOW_WEBHOOK_ORGANISATION` is unset, so `enqueue_zoho_push`
        # returns early and registration costs nothing until it is set.
        #
        # Accepted orphan, as for Person: registering also connects the
        # post_delete SyncRecord reaper, so `Organisation.merge` deleting the
        # absorbed row drops its local record while the CRM Account survives
        # unreferenced (there is no delete endpoint). Org merges are routine —
        # `dedup_key`/`dedupe_organisations` exist because orgs are minted from
        # free-text company strings — so this needs a Limitless-side sweep
        # before the URL is set, not after.
        register_zoho_flow(
            Organisation,
            kind="organisation",
            build_payload=build_organisation_payload,
        )
        for child_model in (PersonEmail, PersonPhone):
            label = child_model._meta.label
            models.signals.post_save.connect(
                _person_channel_changed,
                sender=child_model,
                dispatch_uid=f"integrations.zoho_flow:{label}:post_save",
            )
            models.signals.post_delete.connect(
                _person_channel_changed,
                sender=child_model,
                dispatch_uid=f"integrations.zoho_flow:{label}:post_delete",
            )
        rel_label = PersonRelationship._meta.label
        models.signals.post_save.connect(
            _person_relationship_changed,
            sender=PersonRelationship,
            dispatch_uid=f"integrations.zoho_flow:{rel_label}:post_save",
        )
        models.signals.post_delete.connect(
            _person_relationship_changed,
            sender=PersonRelationship,
            dispatch_uid=f"integrations.zoho_flow:{rel_label}:post_delete",
        )
        # The `:members:` suffix is LOAD-BEARING — do not "tidy" it back to the
        # plain `:post_save` form. `register_zoho_flow` above connects the
        # registry's own handler to Organisation.post_save under exactly
        # `integrations.zoho_flow:accounts.Organisation:post_save`, and Django
        # keys receivers on (dispatch_uid, sender) and keeps the FIRST one — a
        # colliding uid here would be silently dropped, taking the member
        # fan-out with it (guarded by
        # `test_organisation_save_bumps_member_persons`).
        #
        # post_save only: PROTECT on Person.agency means an Organisation with
        # agents can't be deleted, so there is no member-affecting post_delete.
        # (The registry does connect a post_delete SyncRecord reaper for
        # Organisation — different concern, different uid.)
        models.signals.post_save.connect(
            _organisation_changed,
            sender=Organisation,
            dispatch_uid=f"integrations.zoho_flow:{Organisation._meta.label}:members:post_save",
        )
        person_merged.connect(
            _person_merged_receiver,
            dispatch_uid="integrations.zoho_flow:person_merged",
        )
