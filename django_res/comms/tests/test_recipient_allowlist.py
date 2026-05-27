"""Pure unit tests for the recipient allowlist matcher."""

from __future__ import annotations

from comms.recipient_allowlist import filter_recipients


def test_empty_allowlist_is_passthrough() -> None:
    result = filter_recipients(
        to=["guest@example.com"],
        cc=["ops@example.com"],
        bcc=["audit@example.com"],
        allowlist=[],
    )
    assert result.to == ["guest@example.com"]
    assert result.cc == ["ops@example.com"]
    assert result.bcc == ["audit@example.com"]
    assert result.blocked == []


def test_exact_email_match() -> None:
    result = filter_recipients(
        to=["me@villacollective.com", "stranger@elsewhere.com"],
        cc=[],
        bcc=[],
        allowlist=["me@villacollective.com"],
    )
    assert result.to == ["me@villacollective.com"]
    assert result.blocked == ["stranger@elsewhere.com"]


def test_domain_suffix_match() -> None:
    result = filter_recipients(
        to=["alice@villacollective.com", "bob@villacollective.com", "guest@gmail.com"],
        cc=[],
        bcc=[],
        allowlist=["@villacollective.com"],
    )
    assert result.to == ["alice@villacollective.com", "bob@villacollective.com"]
    assert result.blocked == ["guest@gmail.com"]


def test_mixed_entries() -> None:
    result = filter_recipients(
        to=["me@villacollective.com", "ops@partner.com", "guest@gmail.com"],
        cc=[],
        bcc=[],
        allowlist=["@villacollective.com", "ops@partner.com"],
    )
    assert result.to == ["me@villacollective.com", "ops@partner.com"]
    assert result.blocked == ["guest@gmail.com"]


def test_case_insensitive() -> None:
    result = filter_recipients(
        to=["ME@VillaCollective.COM"],
        cc=[],
        bcc=[],
        allowlist=["@villacollective.com"],
    )
    assert result.to == ["ME@VillaCollective.COM"]
    assert result.blocked == []


def test_filters_cc_and_bcc_too() -> None:
    result = filter_recipients(
        to=["me@villacollective.com"],
        cc=["leak@gmail.com"],
        bcc=["audit@villacollective.com", "leak2@gmail.com"],
        allowlist=["@villacollective.com"],
    )
    assert result.to == ["me@villacollective.com"]
    assert result.cc == []
    assert result.bcc == ["audit@villacollective.com"]
    assert sorted(result.blocked) == ["leak2@gmail.com", "leak@gmail.com"]


def test_all_recipients_blocked_returns_empty_to() -> None:
    result = filter_recipients(
        to=["guest@gmail.com"],
        cc=[],
        bcc=[],
        allowlist=["@villacollective.com"],
    )
    assert result.to == []
    assert result.blocked == ["guest@gmail.com"]


def test_whitespace_and_empty_entries_ignored() -> None:
    result = filter_recipients(
        to=["me@villacollective.com"],
        cc=[],
        bcc=[],
        allowlist=["", "   ", " @villacollective.com "],
    )
    assert result.to == ["me@villacollective.com"]
