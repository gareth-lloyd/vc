"""Recipient allowlist filter for outbound email.

When `settings.EMAIL_RECIPIENT_ALLOWLIST` is non-empty, every outbound
recipient must match one of its entries before reaching SMTP. Used on
staging so the demo box can drive real sends to internal addresses
without ever reaching a guest. Empty list = no restriction (production).

Matching rules (case-insensitive):
- exact email entry (`me@example.com`) matches the same address
- domain-suffix entry (`@example.com`) matches any address ending in it
- bare-domain entry (`example.com`) — the `@` is missing — is treated as
  if it were `@example.com`. The staging allowlist is operator-typed,
  and a missing leading `@` is the most common typo. The old behaviour
  silently fell into the exact-match branch and rejected every recipient,
  which on staging means "no test emails get through" — a failure mode
  that is loud enough to debug but loud at the wrong time. Normalising
  defends the staging mailbox without making the operator memorise the
  matcher's syntax.
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


def _normalise_entry(entry: str) -> str:
    """Lower-case, trim, and rewrite a bare domain to `@domain` form.

    A bare-domain typo (`example.com` instead of `@example.com`) used to
    fall into the exact-equality branch and silently reject every
    recipient. Detect "looks like a domain" by the absence of `@` and the
    presence of `.`, and prepend `@` so the existing domain-suffix path
    handles it. Anchoring at `@` also prevents a naive `endswith` from
    matching `evil-example.com` against `example.com`.
    """
    cleaned = entry.strip().lower()
    if cleaned and "@" not in cleaned and "." in cleaned:
        return "@" + cleaned
    return cleaned


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

    Each allowlist entry is normalised: leading/trailing whitespace is
    stripped, casing is folded, and a bare-domain entry (no `@`, but
    with a `.`) is rewritten to `@domain` form so an operator typo
    doesn't silently reject every recipient. See module docstring for
    the rationale.
    """
    if not allowlist:
        return FilterResult(to=list(to), cc=list(cc), bcc=list(bcc), blocked=[])

    normalised = [_normalise_entry(entry) for entry in allowlist if entry.strip()]
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
