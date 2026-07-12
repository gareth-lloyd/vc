"""Cross-cutting field types and range expression helpers.

`CIEmailField` stores emails lowercased; the `citext` extension
(core/migrations) makes DB-side comparison case-insensitive as a backstop.
`DateRangeFunc` / `Int4RangeFunc` build the range expressions used by
ExclusionConstraints.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.contrib.postgres.fields import DateRangeField, IntegerRangeField
from django.db import models

logger = structlog.get_logger(__name__)


class DateRangeFunc(models.Func):
    """`daterange(lower, upper, bounds)` expression for ExclusionConstraints.

    Migrations serialize this by import path (``core.fields.DateRangeFunc``),
    so this module path is permanent once a migration references it.
    """

    function = "daterange"
    output_field = DateRangeField()


class Int4RangeFunc(models.Func):
    """`int4range(lower, upper, bounds)` expression for ExclusionConstraints.

    Same serialization caveat as :class:`DateRangeFunc` — the import path is
    frozen into migrations.
    """

    function = "int4range"
    output_field = IntegerRangeField()


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
            # Decryption failure usually means the row was written with a
            # Fernet key that's been rotated out. Log loudly and return None
            # so downstream consumers can't accidentally treat ciphertext as
            # plaintext (which would be a real security hazard if leaked).
            # Identify the column, never the value — the ciphertext/plaintext
            # must not reach the log.
            model = getattr(self, "model", None)
            logger.exception(
                "encrypted_field.decrypt_failed",
                model=model._meta.label if model is not None else None,
                field=self.name,
            )
            return None

    def get_prep_value(self, value: Any) -> Any:
        if value in (None, ""):
            return value
        from core.encryption import encrypt

        return encrypt(str(value))
