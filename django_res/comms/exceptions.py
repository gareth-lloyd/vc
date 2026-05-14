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
