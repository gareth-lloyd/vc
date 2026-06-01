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

from django.conf import settings
from django.db import IntegrityError, transaction
from django.template import Context, Template

from comms import tasks
from comms.enums import EmailLogStatus, SmtpScope
from comms.exceptions import EmailTemplateNotFound, NoSmtpProfileAvailable
from comms.models import EmailLog, EmailTemplate, SmtpProfile
from comms.recipient_allowlist import filter_recipients

if TYPE_CHECKING:
    from accounts.models import User


RESEND_TOKEN_KEY = "resend_token"
RESENT_FROM_KEY = "resent_from"
BLOCKED_RECIPIENTS_KEY = "blocked_recipients"
BLOCKED_BY_ALLOWLIST_REASON = "All primary recipients blocked by EMAIL_RECIPIENT_ALLOWLIST."


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


def _find_existing_log(idempotency_hash: str) -> EmailLog | None:
    """Return a previously-persisted log row that should dedupe this send.

    Excludes FAILED (the SMTP server refused — caller can retry) and BLOCKED
    (we refused — caller can retry once the gate/allowlist is reopened).
    Treating BLOCKED as a permanent dedupe would silently swallow legitimate
    sends after an allowlist widens.
    """
    return (
        EmailLog.objects.filter(idempotency_hash=idempotency_hash)
        .exclude(status__in=[EmailLogStatus.FAILED, EmailLogStatus.BLOCKED])
        .order_by("-queued_at")
        .first()
    )


def _idempotency_hash(
    *,
    template_key: str,
    to: list[str],
    correlation: dict[str, Any],
) -> str:
    """Hash the *logical* identity of an email — what is being sent, to whom,
    against what business object — not the rendered output or template version.

    Contract: **one template-render per correlation**, not one distinct-body
    per correlation. The dedupe key is `(template_key, sorted(to), correlation)`
    only. The rendered `context`/body is deliberately NOT hashed — two sends of
    the same template to the same recipients against the same business object
    dedupe even if their contexts differ (e.g. a re-fetched booking total). If
    the intent were ever one-distinct-body-per-correlation, the rendered body
    would have to enter the hash; it does not.

    Versioning the hash on `template.version` would likewise re-send the same
    logical event every time ops edits a template (which bumps the active
    version), so a content tweak deployed between two scheduler ticks would
    email the guest twice. The version is captured on the EmailLog row for
    audit but is intentionally excluded from the dedupe key.
    """
    payload = json.dumps(
        {
            "template_key": template_key,
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
            to=to,
            correlation=correlation,
        )

        existing = _find_existing_log(idempotency_hash)
        if existing is not None:
            return existing

        # Recipient allowlist gate. Empty allowlist (production default) is
        # a passthrough; non-empty filters every address and short-circuits
        # to BLOCKED when no primary recipient survives.
        #
        # Persistence rule for `to`/`cc`/`bcc` on the row:
        # - Partial-block (status=SENT): record the *filtered* list — that's
        #   who the message actually went to. Blocked addresses live on
        #   `correlation[BLOCKED_RECIPIENTS_KEY]` for forensics only.
        # - Fully-blocked (status=BLOCKED): record the *original* list so the
        #   admin bulk-resend can recover the row by simply re-queuing it.
        #   `correlation[BLOCKED_RECIPIENTS_KEY]` carries the same data as a
        #   second view for audit, but `to` stays the source of truth for
        #   "who is this message for".
        filtered = filter_recipients(
            to=list(to),
            cc=cc,
            bcc=bcc,
            allowlist=settings.EMAIL_RECIPIENT_ALLOWLIST,
        )
        if filtered.blocked:
            correlation[BLOCKED_RECIPIENTS_KEY] = filtered.blocked
        all_blocked = not filtered.to
        log_to = list(to) if all_blocked else filtered.to
        log_cc = cc if all_blocked else filtered.cc
        log_bcc = bcc if all_blocked else filtered.bcc

        subject = _render(template.subject_template, context)
        body = _render(template.body_template, context)
        body_html = (
            _render(template.body_template_html, context) if template.body_template_html else ""
        )

        from_email = profile.from_email
        # Personal profiles always send "as" the user; otherwise the system
        # profile's configured from_email is the source of truth.
        try:
            with transaction.atomic():
                log = EmailLog.objects.create(
                    template_key=template.key,
                    template_version=template.version,
                    to=log_to,
                    cc=log_cc,
                    bcc=log_bcc,
                    from_email=from_email,
                    sender_user=sender_user if profile.scope == SmtpScope.PERSONAL else None,
                    smtp_profile=profile,
                    rendered_subject=subject,
                    rendered_body=body,
                    rendered_body_html=body_html,
                    status=EmailLogStatus.BLOCKED if all_blocked else EmailLogStatus.QUEUED,
                    failure_reason=BLOCKED_BY_ALLOWLIST_REASON if all_blocked else "",
                    attachments=[a.to_log_entry() for a in attachments],
                    correlation=correlation,
                    idempotency_hash=idempotency_hash,
                )
        except IntegrityError:
            # Concurrent send racing on the same idempotency_hash. The DB
            # `unique_email_log_idempotency_hash` constraint rejected our
            # insert; return the row the winning caller just created.
            existing = _find_existing_log(idempotency_hash)
            if existing is None:
                raise
            return existing

        if not all_blocked:
            tasks.send_email_log.delay(log.pk)  # type: ignore[attr-defined]
        log.refresh_from_db()
        return log

    @classmethod
    def resend(
        cls,
        email_log: EmailLog,
        *,
        actor: User | None,
        idempotency_key: str | None = None,
    ) -> EmailLog:
        """Mint a fresh `EmailLog` row carrying the same content + recipients.

        Used by the operator-facing **Resend** action on the booking
        Comms tab. Distinct from the admin-only `resend_blocked_or_failed`
        bulk action (which
        re-queues a FAILED row in place): this always creates a new row
        so the audit trail shows two distinct send attempts.

        Idempotency: when `idempotency_key` is supplied, a repeat call
        with the same key against the same source row returns the
        previously-minted resend instead of creating another row. This
        is the protection against a double-clicked operator button.

        Sender identity: the resend clones the *original* SmtpProfile and
        ``from_email`` so the guest sees a consistent sender across the
        two send attempts. The operator who clicked Resend is the
        ``actor`` and is captured on the AuditLog row (see
        ``core.audit.track(EmailLog, …)`` in ``comms/apps.py``), not on
        ``sender_user``. If the original profile has been deactivated or
        deleted, fall back to the system profile.
        """
        if idempotency_key:
            existing = (
                EmailLog.objects.filter(
                    correlation__resent_from=email_log.pk,
                    correlation__resend_token=idempotency_key,
                )
                .order_by("queued_at")
                .first()
            )
            if existing is not None:
                return existing

        if email_log.smtp_profile is not None and email_log.smtp_profile.is_active:
            profile = email_log.smtp_profile
            from_email = email_log.from_email
        else:
            profile = cls._resolve_profile(None)
            from_email = profile.from_email

        new_correlation = dict(email_log.correlation or {})
        new_correlation[RESENT_FROM_KEY] = email_log.pk
        if idempotency_key:
            new_correlation[RESEND_TOKEN_KEY] = idempotency_key

        # Resend must honour the same allowlist as send — operator action
        # is not a loophole. The persistence rule for `to` mirrors `send`:
        # filtered subset on partial-block (SENT), originals on fully-blocked
        # (BLOCKED) so the recovery path doesn't have to peek into
        # `correlation` to know who the message was for.
        original_to = list(email_log.to)
        original_cc = list(email_log.cc)
        original_bcc = list(email_log.bcc)
        filtered = filter_recipients(
            to=original_to,
            cc=original_cc,
            bcc=original_bcc,
            allowlist=settings.EMAIL_RECIPIENT_ALLOWLIST,
        )
        if filtered.blocked:
            new_correlation[BLOCKED_RECIPIENTS_KEY] = filtered.blocked
        all_blocked = not filtered.to
        log_to = original_to if all_blocked else filtered.to
        log_cc = original_cc if all_blocked else filtered.cc
        log_bcc = original_bcc if all_blocked else filtered.bcc

        with transaction.atomic():
            new_log = EmailLog.objects.create(
                template_key=email_log.template_key,
                template_version=email_log.template_version,
                to=log_to,
                cc=log_cc,
                bcc=log_bcc,
                from_email=from_email,
                sender_user=email_log.sender_user,
                smtp_profile=profile,
                rendered_subject=email_log.rendered_subject,
                rendered_body=email_log.rendered_body,
                rendered_body_html=email_log.rendered_body_html,
                status=EmailLogStatus.BLOCKED if all_blocked else EmailLogStatus.QUEUED,
                failure_reason=BLOCKED_BY_ALLOWLIST_REASON if all_blocked else "",
                attachments=list(email_log.attachments or []),
                correlation=new_correlation,
            )
            # Defer dispatch until commit so the Celery worker can always
            # read back the new row — bare .delay() inside the block races
            # the commit, and on_commit also defers correctly when a
            # caller wraps resend() in an outer transaction.
            new_log_pk = new_log.pk

            if not all_blocked:

                def _dispatch() -> None:
                    tasks.send_email_log.delay(new_log_pk)  # type: ignore[attr-defined]

                transaction.on_commit(_dispatch)

        new_log.refresh_from_db()
        return new_log

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
