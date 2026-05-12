"""EmailService — single entry point for transactional email.

Resolves the active ``EmailTemplate``, renders it with the provided context,
picks an ``SmtpProfile`` (personal-of-sender then system fallback), persists
an ``EmailLog`` row in ``QUEUED`` state and hands it off to
``comms.tasks.send_email_log`` for actual dispatch.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.template import Context, Template

from comms import tasks
from comms.enums import EmailLogStatus, SmtpScope
from comms.exceptions import EmailTemplateNotFound, NoSmtpProfileAvailable
from comms.models import EmailLog, EmailTemplate, SmtpProfile

if TYPE_CHECKING:
    from accounts.models import User


@dataclass(frozen=True)
class Attachment:
    """Reference to an attachment stored on object storage.

    The binary content lives on S3 (or MinIO locally); the log row carries
    only the metadata needed to re-fetch and re-attach when the message is
    rendered for delivery.
    """

    filename: str
    content_type: str
    size: int
    storage_key: str

    def to_log_entry(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "content_type": self.content_type,
            "size": self.size,
            "storage_key": self.storage_key,
        }


def _render(template_text: str, context: dict[str, Any]) -> str:
    return Template(template_text).render(Context(context))


def _idempotency_hash(
    *,
    template_key: str,
    template_version: int,
    to: list[str],
    correlation: dict[str, Any],
) -> str:
    payload = json.dumps(
        {
            "template_key": template_key,
            "template_version": template_version,
            "to": sorted(to),
            "correlation": correlation,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EmailService:
    """Stateless email dispatch service."""

    @classmethod
    def send(
        cls,
        *,
        template_key: str,
        context: dict[str, Any],
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        sender_user: User | None = None,
        attachments: list[Attachment] | None = None,
        correlation: dict[str, Any] | None = None,
    ) -> EmailLog:
        """Render and dispatch an email; returns the persisted ``EmailLog`` row.

        Re-emission of the same logical event (same template, version,
        recipients, correlation) returns the existing row instead of
        creating a duplicate.
        """
        cc = list(cc or [])
        bcc = list(bcc or [])
        correlation = dict(correlation or {})
        attachments = list(attachments or [])

        template = cls._resolve_template(template_key)
        profile = cls._resolve_profile(sender_user)

        idempotency_hash = _idempotency_hash(
            template_key=template.key,
            template_version=template.version,
            to=to,
            correlation=correlation,
        )

        existing = (
            EmailLog.objects.filter(idempotency_hash=idempotency_hash)
            .exclude(status=EmailLogStatus.FAILED)
            .order_by("-queued_at")
            .first()
        )
        if existing is not None:
            return existing

        subject = _render(template.subject_template, context)
        body = _render(template.body_template, context)

        from_email = profile.from_email
        # Personal profiles always send "as" the user; otherwise the system
        # profile's configured from_email is the source of truth.
        with transaction.atomic():
            log = EmailLog.objects.create(
                template_key=template.key,
                template_version=template.version,
                to=list(to),
                cc=cc,
                bcc=bcc,
                from_email=from_email,
                sender_user=sender_user if profile.scope == SmtpScope.PERSONAL else None,
                smtp_profile=profile,
                rendered_subject=subject,
                rendered_body=body,
                status=EmailLogStatus.QUEUED,
                attachments=[a.to_log_entry() for a in attachments],
                correlation=correlation,
                idempotency_hash=idempotency_hash,
            )

        tasks.send_email_log.delay(log.pk)  # type: ignore[attr-defined]
        log.refresh_from_db()
        return log

    @staticmethod
    def _resolve_template(template_key: str) -> EmailTemplate:
        template = EmailTemplate.objects.filter(key=template_key, is_active=True).first()
        if template is None:
            raise EmailTemplateNotFound(f"No active template for key {template_key!r}.")
        return template

    @staticmethod
    def _resolve_profile(sender_user: User | None) -> SmtpProfile:
        if sender_user is not None:
            personal = (
                SmtpProfile.objects.filter(
                    owner=sender_user,
                    scope=SmtpScope.PERSONAL,
                    is_active=True,
                )
                .order_by("-updated_at")
                .first()
            )
            if personal is not None:
                return personal

        system = (
            SmtpProfile.objects.filter(scope=SmtpScope.SYSTEM, is_active=True)
            .order_by("-updated_at")
            .first()
        )
        if system is None:
            raise NoSmtpProfileAvailable("No active SYSTEM SmtpProfile configured.")
        return system
