"""Structured-logging primitives (structlog processors + configuration).

Lives in ``core`` (the foundation) so every app can emit structured logs
without a cross-app import. Imports only stdlib + ``core.audit.REDACTED`` —
no domain-app edges, keeping the import-linter ``core``-foundation contract
intact.

- ``redaction.redact_sensitive`` — denylist + value-pattern PII redaction.
- ``processors.add_static_fields`` / ``processors.drop_noisy_requests``.
- ``config.configure_structlog`` — wires structlog + the ``LOGGING`` dict.
"""
