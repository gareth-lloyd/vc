"""GAP-094 — `_send` re-fetches attachment bytes and attaches them.

`EmailLog.attachments` carries only metadata (the row is JSON, not a blob);
the binary lives in an object-storage alias and is re-read at dispatch time.
The fetch sits in its own `try` **before** the message is built, because
`FileNotFoundError` is an `OSError` and the SMTP classifier would otherwise
read a permanently-missing object as a retryable network blip and burn six
retries on it.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.storage import storages

from comms.enums import EmailLogStatus
from comms.models import EmailLog, EmailTemplate, SmtpProfile
from comms.services import Attachment
from comms.tasks import TransientEmailError, _send

PDF_BYTES = b"%PDF-1.7\nattachment-test\n"


@pytest.fixture
def template(db: None) -> EmailTemplate:
    return EmailTemplate.objects.create(
        key="test.attachments",
        version=1,
        subject_template="x",
        title="x",
    )


@pytest.fixture
def stored_pdf() -> str:
    """Write a PDF into the private `documents` alias; return its key."""
    return storages["documents"].save("test-attachments/contract.pdf", ContentFile(PDF_BYTES))


def _queued_log(
    template: EmailTemplate,
    profile: SmtpProfile,
    attachments: list[dict[str, object]],
) -> EmailLog:
    return EmailLog.objects.create(
        template_key=template.key,
        template_version=template.version,
        to=["guest@villacollective.com"],
        cc=[],
        bcc=[],
        from_email=profile.from_email,
        sender_user=None,
        smtp_profile=profile,
        rendered_subject="Your contract",
        rendered_body="Attached.",
        rendered_body_html="<p>Attached.</p>",
        status=EmailLogStatus.QUEUED,
        attachments=attachments,
        correlation={},
        idempotency_hash=f"manual-attachment-test-{len(attachments)}-{id(attachments)}",
    )


# ----------------------------------------------------------------------
# Attachment metadata
# ----------------------------------------------------------------------
def test_to_log_entry_carries_the_storage_alias() -> None:
    entry = Attachment(
        filename="BK-1-contract-3.pdf",
        content_type="application/pdf",
        size=len(PDF_BYTES),
        storage_key="booking_documents/2026/09/x.pdf",
        storage="documents",
    ).to_log_entry()

    assert entry == {
        "filename": "BK-1-contract-3.pdf",
        "content_type": "application/pdf",
        "size": len(PDF_BYTES),
        "storage_key": "booking_documents/2026/09/x.pdf",
        "storage": "documents",
    }


def test_attachment_storage_defaults_to_the_default_alias() -> None:
    entry = Attachment(
        filename="x.pdf", content_type="application/pdf", size=1, storage_key="k"
    ).to_log_entry()

    assert entry["storage"] == "default"


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_send_attaches_the_stored_object(
    system_profile: SmtpProfile,
    template: EmailTemplate,
    stored_pdf: str,
) -> None:
    log = _queued_log(
        template,
        system_profile,
        [
            {
                "filename": "BK-1-contract-3.pdf",
                "content_type": "application/pdf",
                "size": len(PDF_BYTES),
                "storage_key": stored_pdf,
                "storage": "documents",
            }
        ],
    )
    mail.outbox.clear()

    _send(log.pk)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].attachments == [("BK-1-contract-3.pdf", PDF_BYTES, "application/pdf")]
    log.refresh_from_db()
    assert log.status == EmailLogStatus.SENT


@pytest.mark.django_db
def test_entry_without_a_storage_key_reads_the_default_alias(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    """Rows written before the alias existed must still dispatch."""
    key = storages["default"].save("test-attachments/legacy.pdf", ContentFile(PDF_BYTES))
    log = _queued_log(
        template,
        system_profile,
        [
            {
                "filename": "legacy.pdf",
                "content_type": "application/pdf",
                "size": len(PDF_BYTES),
                "storage_key": key,
            }
        ],
    )
    mail.outbox.clear()

    _send(log.pk)

    assert mail.outbox[0].attachments == [("legacy.pdf", PDF_BYTES, "application/pdf")]


@pytest.mark.django_db
def test_no_attachments_is_unaffected(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    log = _queued_log(template, system_profile, [])
    mail.outbox.clear()

    _send(log.pk)

    assert mail.outbox[0].attachments == []
    log.refresh_from_db()
    assert log.status == EmailLogStatus.SENT


# ----------------------------------------------------------------------
# Failure classification
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_missing_object_fails_permanently_without_retrying(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    log = _queued_log(
        template,
        system_profile,
        [
            {
                "filename": "gone.pdf",
                "content_type": "application/pdf",
                "size": 10,
                "storage_key": "test-attachments/never-written.pdf",
                "storage": "documents",
            }
        ],
    )
    mail.outbox.clear()

    _send(log.pk)  # must not raise TransientEmailError

    log.refresh_from_db()
    assert log.status == EmailLogStatus.FAILED
    assert "gone.pdf" in log.failure_reason
    assert mail.outbox == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "exc",
    [
        EndpointConnectionError(endpoint_url="https://s3.example"),
        ReadTimeoutError(endpoint_url="https://s3.example"),
        ClientError({"ResponseMetadata": {"HTTPStatusCode": 503}}, "GetObject"),
        ConnectionResetError("connection reset by peer"),
    ],
    ids=["endpoint", "read-timeout", "s3-5xx", "socket"],
)
def test_transient_storage_error_retries_and_leaves_the_row_queued(
    system_profile: SmtpProfile,
    template: EmailTemplate,
    stored_pdf: str,
    exc: Exception,
) -> None:
    log = _queued_log(
        template,
        system_profile,
        [
            {
                "filename": "x.pdf",
                "content_type": "application/pdf",
                "size": 1,
                "storage_key": stored_pdf,
                "storage": "documents",
            }
        ],
    )
    mail.outbox.clear()

    with patch("comms.tasks.storages") as fake_storages:
        fake_storages.__getitem__.return_value.open.side_effect = exc
        with pytest.raises(TransientEmailError):
            _send(log.pk)

    log.refresh_from_db()
    assert log.status == EmailLogStatus.QUEUED
    assert mail.outbox == []


@pytest.mark.django_db
def test_client_error_below_500_fails_permanently(
    system_profile: SmtpProfile,
    template: EmailTemplate,
    stored_pdf: str,
) -> None:
    """A 403/404 from S3 is a configuration or lifecycle problem — retrying
    six times just re-fails and delays the FAILED row an operator acts on."""
    log = _queued_log(
        template,
        system_profile,
        [
            {
                "filename": "x.pdf",
                "content_type": "application/pdf",
                "size": 1,
                "storage_key": stored_pdf,
                "storage": "documents",
            }
        ],
    )

    with patch("comms.tasks.storages") as fake_storages:
        fake_storages.__getitem__.return_value.open.side_effect = ClientError(
            {"ResponseMetadata": {"HTTPStatusCode": 403}}, "GetObject"
        )
        _send(log.pk)

    log.refresh_from_db()
    assert log.status == EmailLogStatus.FAILED


@pytest.mark.django_db
def test_unknown_storage_alias_fails_permanently(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    log = _queued_log(
        template,
        system_profile,
        [
            {
                "filename": "x.pdf",
                "content_type": "application/pdf",
                "size": 1,
                "storage_key": "k",
                "storage": "nope",
            }
        ],
    )

    _send(log.pk)

    log.refresh_from_db()
    assert log.status == EmailLogStatus.FAILED


@pytest.mark.django_db
def test_malformed_entry_fails_permanently(
    system_profile: SmtpProfile,
    template: EmailTemplate,
    stored_pdf: str,
) -> None:
    """A row missing `filename`/`content_type` must be classified, not crash.

    An unclassified exception out of `_send` leaves the row QUEUED, and
    `requeue_stuck_emails` then re-dispatches it every grace window forever.
    """
    log = _queued_log(
        template,
        system_profile,
        [{"storage_key": stored_pdf, "storage": "documents"}],
    )

    _send(log.pk)

    log.refresh_from_db()
    assert log.status == EmailLogStatus.FAILED
