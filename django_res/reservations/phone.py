"""Phone-number normalization to E.164.

One rule, reused by every write path (API, admin, data-migration loaders):
parse with `phonenumbers`, store the canonical E.164 form when the number is
valid, and **never raise or drop data** — an unparseable value passes through
trimmed and unchanged so a messy legacy import is preserved rather than lost.
"""

from __future__ import annotations

import phonenumbers


def to_e164(
    raw: str | None,
    *,
    region: str | None = None,
    country_code: str | None = None,
) -> str:
    """Return `raw` as an E.164 string, or the trimmed raw input if unparseable.

    - `region`: ISO-3166 alpha-2 (e.g. ``"GB"``) used to anchor a national
      number that lacks a ``+`` prefix.
    - `country_code`: a legacy numeric calling code (e.g. ``"44"``); resolved to
      a region when `region` isn't supplied. This is the shape the legacy SQL
      Server dump stores.

    Empty / blank / ``None`` input returns ``""``.
    """
    if not raw:
        return ""
    trimmed = str(raw).strip()
    if not trimmed:
        return ""

    parse_region = region or _region_from_calling_code(country_code)

    try:
        parsed = phonenumbers.parse(trimmed, parse_region)
    except phonenumbers.NumberParseException:
        return trimmed

    if phonenumbers.is_valid_number(parsed):
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    return trimmed


def _region_from_calling_code(country_code: str | None) -> str | None:
    """Map a numeric calling code (``"44"``) to an ISO region (``"GB"``)."""
    if not country_code:
        return None
    try:
        cc_int = int(str(country_code).lstrip("+").strip())
    except (TypeError, ValueError):
        return None
    region = phonenumbers.region_code_for_country_code(cc_int)
    # `region_code_for_country_code` returns "ZZ" for unknown codes.
    return region if region and region != "ZZ" else None
