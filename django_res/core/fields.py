"""Cross-cutting field types.

Includes a CIEmailField that falls back to a case-insensitive lookup on
SQLite (which has no citext extension). On Postgres, override behaviour is
to enforce case-insensitivity via the database extension migration in
core/migrations.
"""

from __future__ import annotations

from typing import Any

from django.db import models


class CIEmailField(models.EmailField):
    """Email field stored lowercased to enforce case-insensitive comparison.

    Backed by the `citext` extension on Postgres (configured in core
    migrations), but the lowercasing here ensures the value is canonical
    regardless of backend — Postgres `citext` is a redundancy that
    guarantees comparison semantics.
    """

    def get_prep_value(self, value: Any) -> Any:
        value = super().get_prep_value(value)
        if isinstance(value, str):
            return value.lower()
        return value

    def pre_save(self, model_instance: models.Model, add: bool) -> Any:
        value = super().pre_save(model_instance, add)
        if isinstance(value, str):
            value = value.lower()
            setattr(model_instance, self.attname, value)
        return value


class EncryptedTextField(models.TextField):
    """Fernet-encrypted TextField. Wraps cleartext on save, unwraps on load.

    Empty strings are stored as empty strings (we don't want to encrypt a zero
    byte payload and burn ciphertext on the placeholder case).
    """

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> Any:
        if value in (None, ""):
            return value
        from core.encryption import decrypt

        try:
            return decrypt(value)
        except Exception:
            # If decryption fails it almost always means the row was written
            # with a key that has been rotated out. Surface the ciphertext
            # rather than raise so admin pages still render — services that
            # care will fail validating downstream.
            return value

    def get_prep_value(self, value: Any) -> Any:
        if value in (None, ""):
            return value
        from core.encryption import encrypt

        return encrypt(str(value))
