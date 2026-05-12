"""Fernet wrapper used by tfa_secret / smtp passwords / OAuth tokens.

Reads `settings.FERNET_KEYS` (list of base64 32-byte keys). The list is
oldest-first for decryption; encryption uses the newest (last) key.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings


def _get_multi_fernet() -> MultiFernet:
    keys = settings.FERNET_KEYS
    if not keys:
        raise RuntimeError("FERNET_KEYS is empty — refusing to encrypt with no key.")
    # MultiFernet uses the first key to encrypt; we keep newest-first for that.
    return MultiFernet([Fernet(k) for k in reversed(keys)])


def encrypt(value: str) -> str:
    if value == "":
        return ""
    return _get_multi_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(value: str) -> str:
    if value == "":
        return ""
    return _get_multi_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
