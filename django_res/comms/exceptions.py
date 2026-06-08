"""Domain errors raised by comms services."""

from __future__ import annotations

from core.exceptions import DomainError


class EmailTemplateNotFound(DomainError):
    code = "email_template_not_found"


class NoSmtpProfileAvailable(DomainError):
    code = "no_smtp_profile_available"


class MjmlCompileError(DomainError):
    code = "mjml_compile_error"
    status_code = 400

    def __init__(self, message: str, *, source: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.source = source
        self.errors = errors or []
        # The compiler errors always pertain to the MJML source; surface them
        # under that field so the canonical handler reports them as
        # `field_errors` rather than a bespoke key.
        self.field_errors = {"body_template_mjml": self.errors or [message]}


class TemplatePublishError(DomainError):
    """A draft template failed validation and must not be published.

    Raised by ``EmailTemplateService.publish_version`` when the submitted
    MJML fails to compile or any of the rendered fields (subject, plaintext
    body, compiled HTML) contains a malformed Django template tag. Carries
    the per-field errors so the API can surface exactly what to fix.
    Mapped to HTTP 400 — this is malformed input, not a state conflict.
    """

    code = "template_publish_error"
    status_code = 400

    def __init__(self, message: str, *, field_errors: dict[str, list[str]] | None = None) -> None:
        super().__init__(message)
        self.field_errors = field_errors or {}


class TemplateRenderError(DomainError):
    """A draft template failed to render during preview.

    The read-only-preview analogue of ``TemplatePublishError``: a malformed
    Django tag in a draft surfaces as HTTP 400 carrying the offending field,
    never a 500.
    """

    code = "template_render_error"
    status_code = 400

    def __init__(self, message: str, *, field_errors: dict[str, list[str]] | None = None) -> None:
        super().__init__(message)
        self.field_errors = field_errors or {}
