"""Domain errors raised by comms services."""

from __future__ import annotations

from core.exceptions import DomainError


class EmailTemplateNotFound(DomainError):
    code = "email_template_not_found"


class NoSmtpProfileAvailable(DomainError):
    code = "no_smtp_profile_available"
