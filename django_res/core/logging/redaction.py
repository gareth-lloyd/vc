"""PII-redaction structlog processor.

Defense in depth for the design mandate "never log email bodies / PII"
(``django_res_design/design/departures.md``). Engineer discipline is the first
line; this processor is the structural backstop that scrubs sensitive values
out of every log line *before* it is rendered.

Two mechanisms, both conservative:

- **Key denylist.** A key marks its value for redaction if it *contains* one of
  the unambiguous long tokens (``password``, ``secret``, ``token``, …) or has one
  of the short/ambiguous tokens (``card``, ``pan``, ``otp``, ``body``, …) as a
  whole ``_``/``-``-delimited word. Whole-word matching for the short tokens is
  deliberate: a bare ``in`` test would redact benign keys like ``panel`` (⊃
  ``pan``), ``wildcard`` (⊃ ``card``) or ``response_body`` parts of ``somebody``.
- **Value patterns.** String values (under a size cap, to skip large blobs) are
  scrubbed for a ``Bearer`` token or a Luhn-valid card PAN. Only the matched
  span is replaced — the surrounding text survives — and the PAN match must pass
  the Luhn checksum, so a benign 13-19 digit identifier is not destroyed.

Redaction recurses into nested dicts and lists — engineers routinely log
nested structures (``guest={"email": …, "card": …}``), so a top-level-only
sweep would leak.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from core.audit import REDACTED

if TYPE_CHECKING:
    from structlog.types import EventDict, WrappedLogger

# Tokens unambiguous enough to match anywhere in the key — they don't occur
# inside benign English/identifier words, so a substring test is safe and
# catches compounds (``access_token``, ``smtp_password``, ``stripe_api_key``).
_SUBSTRING_TOKENS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "authorization",
        "api_key",
        "apikey",
        "card_number",
        "fernet",
        "totp",
        "ssn",
    }
)

# Short/ambiguous tokens that must match as a whole ``_``/``-``-delimited word,
# so ``panel``/``wildcard``/``somebody`` are *not* redacted but ``card_number``
# (word "card"), ``email_body`` (word "body") and a bare ``otp`` are.
_WORD_TOKENS: frozenset[str] = frozenset({"card", "pan", "otp", "cvv", "cvc", "pin", "body"})

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")

# Value-pattern backstop. Bounded to short strings so we never scan a large
# payload on every log line.
_VALUE_SCAN_MAX_LEN = 2048
_PAN_RE = re.compile(r"\b\d{13,19}\b")
_BEARER_RE = re.compile(r"bearer\s+\S+", re.IGNORECASE)


def _key_is_sensitive(key: str) -> bool:
    lowered = key.lower()
    if any(token in lowered for token in _SUBSTRING_TOKENS):
        return True
    words = set(_WORD_SPLIT.split(lowered))
    return bool(words & _WORD_TOKENS)


def _luhn_valid(digits: str) -> bool:
    """Luhn checksum — true for real card PANs, ~90% of random digit runs fail."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = ord(char) - 48
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _scrub_value_patterns(value: str) -> str:
    """Replace only ``Bearer``/Luhn-valid-PAN spans, leaving benign text intact."""
    if len(value) > _VALUE_SCAN_MAX_LEN:
        return value
    scrubbed = _BEARER_RE.sub(REDACTED, value)
    return _PAN_RE.sub(lambda m: REDACTED if _luhn_valid(m.group()) else m.group(), scrubbed)


def _redact_value(value: Any) -> Any:
    """Recursively redact a value (called for non-sensitive top-level keys)."""
    if isinstance(value, dict):
        return {
            key: REDACTED if _key_is_sensitive(str(key)) else _redact_value(inner)
            for key, inner in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _scrub_value_patterns(value)
    return value


def redact_sensitive(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """structlog processor: scrub sensitive keys/values from ``event_dict``."""
    for key in list(event_dict.keys()):
        if _key_is_sensitive(str(key)):
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict
