"""Unit tests for the PII-redaction processor (pure function, no DB)."""

from __future__ import annotations

from typing import Any

from core.audit import REDACTED
from core.logging.redaction import redact_sensitive


def _redact(event_dict: dict[str, Any]) -> dict[str, Any]:
    return dict(redact_sensitive(None, "info", event_dict))


def test_denylisted_top_level_keys_are_redacted() -> None:
    out = _redact(
        {
            "event": "auth.login",
            "password": "hunter2",
            "access_token": "abc.def",
            "stripe_secret": "sk_live_x",
            "authorization": "Basic Zm9v",
            "smtp_password": "p",
        }
    )
    assert out["password"] == REDACTED
    assert out["access_token"] == REDACTED
    assert out["stripe_secret"] == REDACTED
    assert out["authorization"] == REDACTED
    assert out["smtp_password"] == REDACTED
    # Benign keys pass through untouched.
    assert out["event"] == "auth.login"


def test_benign_keys_pass_through() -> None:
    out = _redact({"event": "booking.created", "booking_id": 42, "nights": 7})
    assert out == {"event": "booking.created", "booking_id": 42, "nights": 7}


def test_nested_dicts_and_lists_are_redacted() -> None:
    out = _redact(
        {
            "event": "guest.synced",
            "guest": {"email": "a@b.com", "card_number": "4111111111111111", "name": "Ada"},
            "entries": [{"refresh_token": "r1"}, {"id": 9}],
        }
    )
    assert out["guest"]["card_number"] == REDACTED
    assert out["guest"]["name"] == "Ada"
    # `email` is not denylisted by key (we keep contact emails); only bodies are.
    assert out["guest"]["email"] == "a@b.com"
    # Nested under a benign list key: the sensitive inner key is still scrubbed.
    assert out["entries"][0]["refresh_token"] == REDACTED
    assert out["entries"][1]["id"] == 9


def test_denylisted_collection_key_redacts_wholesale() -> None:
    # A key that itself reads as secret (`tokens` ⊃ `token`) is replaced
    # entirely, without descending — the safe, conservative default.
    out = _redact({"event": "x", "tokens": [{"id": 1}, {"id": 2}]})
    assert out["tokens"] == REDACTED


def test_value_patterns_redact_only_the_matched_span() -> None:
    # 4111111111111111 is a Luhn-valid Visa test PAN; only that span is
    # scrubbed, the surrounding text survives.
    out = _redact(
        {
            "event": "webhook.received",
            "note": "card 4111111111111111 declined",
            "header": "Bearer eyJhbGciOiJIUzI1Nialong.token",
            "plain": "nothing to see",
        }
    )
    assert out["note"] == f"card {REDACTED} declined"
    assert out["header"] == REDACTED
    assert out["plain"] == "nothing to see"


def test_benign_digit_run_is_not_redacted() -> None:
    # 4111111111111112 fails the Luhn checksum — a benign 13-19 digit
    # identifier must not be destroyed by the PAN backstop.
    out = _redact({"event": "x", "note": "ref 4111111111111112 ok"})
    assert out["note"] == "ref 4111111111111112 ok"


def test_short_token_keys_match_only_as_whole_words() -> None:
    # `panel`/`wildcard` contain `pan`/`card` as substrings but must NOT be
    # redacted; `card_number` (word "card") and a bare `otp` still are.
    out = _redact({"event": "x", "panel": "left", "wildcard": "*", "otp": "123456"})
    assert out["panel"] == "left"
    assert out["wildcard"] == "*"
    assert out["otp"] == REDACTED


def test_oversized_value_is_not_scanned() -> None:
    # A large blob that happens to contain a PAN-like run is skipped by the
    # size cap (we never regex-scan big payloads on the hot path).
    big = "x" * 5000 + "4111111111111111"
    out = _redact({"event": "x", "blob": big})
    assert out["blob"] == big
