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


def test_bare_domain_entry_treated_as_at_domain() -> None:
    """A bare domain (forgot the leading `@`) is treated as a domain-suffix
    rule, not silently rejected as a malformed exact-match entry.

    The staging allowlist is operator-typed; a missing `@` is the most
    common typo and historically caused every recipient to be blocked.
    Normalising defends the staging mailbox without forcing the operator
    to know the matcher's syntax.
    """
    result = filter_recipients(
        to=["alice@villacollective.com", "bob@villacollective.com", "guest@gmail.com"],
        cc=[],
        bcc=[],
        allowlist=["villacollective.com"],
    )
    assert result.to == ["alice@villacollective.com", "bob@villacollective.com"]
    assert result.blocked == ["guest@gmail.com"]


def test_at_domain_entry_still_matches() -> None:
    """Regression guard: normalising bare-domain entries must not break the
    canonical `@domain` form.
    """
    result = filter_recipients(
        to=["alice@villacollective.com", "guest@gmail.com"],
        cc=[],
        bcc=[],
        allowlist=["@villacollective.com"],
    )
    assert result.to == ["alice@villacollective.com"]
    assert result.blocked == ["guest@gmail.com"]


def test_bare_domain_does_not_swallow_subdomain_of_other_domain() -> None:
    """`villacollective.com` must not match `evil-villacollective.com`.

    A naive endswith without the `@` prefix would; normalising to
    `@villacollective.com` anchors the match at the host boundary.
    """
    result = filter_recipients(
        to=["leak@evil-villacollective.com"],
        cc=[],
        bcc=[],
        allowlist=["villacollective.com"],
    )
    assert result.to == []
    assert result.blocked == ["leak@evil-villacollective.com"]
