"""Serializers for the `/email-templates/*` admin API.

List/detail/write split per `django_res/CLAUDE.md`. Publishing and preview go
through `EmailTemplateService`, not `serializer.save()`, so the write/request
serializers are plain `Serializer`s used purely for input validation.
"""

from __future__ import annotations

from rest_framework import serializers

from comms.models import EmailTemplate


class EmailTemplateListSerializer(serializers.ModelSerializer):
    """The active-template catalogue row — no bodies, just identity + provenance."""

    updated_by_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = EmailTemplate
        fields: tuple[str, ...] = (
            "key",
            "version",
            "is_active",
            "updated_at",
            "updated_by_id",
        )
        read_only_fields = fields


class EmailTemplateDetailSerializer(EmailTemplateListSerializer):
    """A single version with its full authored + compiled bodies.

    `body_template_html` is the compiled output of `body_template_mjml`,
    recomputed on every model save — surfaced read-only, never accepted.
    """

    class Meta(EmailTemplateListSerializer.Meta):
        fields: tuple[str, ...] = (
            *EmailTemplateListSerializer.Meta.fields,
            "subject_template",
            "body_template",
            "body_template_mjml",
            "body_template_html",
            "notes",
        )
        read_only_fields = fields


class EmailTemplatePublishSerializer(serializers.Serializer):
    """PUT body for publishing a new active version.

    `body_template_html` is intentionally absent — it's derived from the MJML.
    """

    subject_template = serializers.CharField()
    body_template = serializers.CharField()
    body_template_mjml = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class EmailTemplatePreviewRequestSerializer(serializers.Serializer):
    """POST body for `:preview`.

    Context sources (explicit `context` wins): a synthetic `context` dict, or a
    real `booking_id` / `quotation_id` to render against. Optional draft
    overrides let the editor preview unsaved edits — when any override is
    present the active row fills in the rest.

    The `context` dict is read straight from `request.data` in the view rather
    than declared here: `context` is a reserved attribute on DRF serializers,
    so a field of that name would shadow `Serializer.context`.
    """

    booking_id = serializers.IntegerField(required=False)
    quotation_id = serializers.IntegerField(required=False)
    # Draft overrides (preview-before-publish loop).
    subject_template = serializers.CharField(required=False, allow_blank=True)
    body_template = serializers.CharField(required=False, allow_blank=True)
    body_template_mjml = serializers.CharField(required=False, allow_blank=True)


class TestSendRequestSerializer(serializers.Serializer):
    """POST body for `:test-send`. `to` defaults to the caller's own email.

    As with preview, the `context` dict is read from `request.data` in the view.
    """

    to = serializers.EmailField(required=False)
    booking_id = serializers.IntegerField(required=False)
    quotation_id = serializers.IntegerField(required=False)
