"""Recipient allowlist filter for outbound email.

When `settings.EMAIL_RECIPIENT_ALLOWLIST` is non-empty, every outbound
recipient must match one of its entries before reaching SMTP. Used on
staging so the demo box can drive real sends to internal addresses
without ever reaching a guest. Empty list = no restriction (production).

Matching rules (case-insensitive):
- exact email entry (`me@example.com`) matches the same address
- domain-suffix entry (`@example.com`) matches any address ending in it
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FilterResult:
    to: list[str]
    cc: list[str]
    bcc: list[str]
    blocked: list[str]


def _is_allowed(address: str, normalised_allowlist: list[str]) -> bool:
    addr = address.strip().lower()
    for entry in normalised_allowlist:
        if entry.startswith("@"):
            if addr.endswith(entry):
                return True
        elif addr == entry:
            return True
    return False


def filter_recipients(
    *,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    allowlist: list[str],
) -> FilterResult:
    """Filter `to`/`cc`/`bcc` through the allowlist; report blocked addresses.

    Empty allowlist short-circuits to a passthrough — callers don't need
    to special-case production.
    """
    if not allowlist:
        return FilterResult(to=list(to), cc=list(cc), bcc=list(bcc), blocked=[])

    normalised = [entry.strip().lower() for entry in allowlist if entry.strip()]
    blocked: list[str] = []

    def _split(addresses: list[str]) -> list[str]:
        allowed: list[str] = []
        for addr in addresses:
            if _is_allowed(addr, normalised):
                allowed.append(addr)
            else:
                blocked.append(addr)
        return allowed

    return FilterResult(
        to=_split(to),
        cc=_split(cc),
        bcc=_split(bcc),
        blocked=blocked,
    )
