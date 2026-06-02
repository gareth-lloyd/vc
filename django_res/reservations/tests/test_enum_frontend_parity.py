"""Contract test: concierge enums stay in lock-step with the frontend.

The matrix renders one column per `ConciergeService` and one fill per
`ServiceStatus`. The frontend hard-codes the same lists (`SERVICE_KEYS` in
`styles/tokens.ts`, `SERVICE_STATUSES` in `components/data/ServiceDot.tsx`).
If the two drift, columns silently misalign or a cell renders untyped. This
test fails loudly on drift instead of letting it reach a browser.

Backend-only checkouts (no frontend tree) skip rather than fail.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings

from reservations.enums import ConciergeService, ServiceStatus

FRONTEND_DIR = Path(settings.BASE_DIR).parent / "frontend"
TOKENS_TS = FRONTEND_DIR / "src" / "styles" / "tokens.ts"
SERVICE_DOT_TSX = FRONTEND_DIR / "src" / "components" / "data" / "ServiceDot.tsx"


def _extract_string_array(source: Path, const_name: str) -> list[str]:
    """Pull the quoted tokens out of an ``export const NAME = [ … ] as const;``.

    Anchored to the named block so reformatting (one-per-line vs inline) and
    other arrays in the same file don't perturb the result.
    """
    text = source.read_text(encoding="utf-8")
    match = re.search(
        rf"export const {re.escape(const_name)}\s*=\s*\[(.*?)\]",
        text,
        re.DOTALL,
    )
    assert match is not None, f"Could not find `export const {const_name} = [` in {source}"
    return re.findall(r"""['"]([^'"]+)['"]""", match.group(1))


@pytest.mark.skipif(not TOKENS_TS.exists(), reason="frontend tree not present in this checkout")
def test_service_keys_match_concierge_service_enum() -> None:
    frontend_keys = _extract_string_array(TOKENS_TS, "SERVICE_KEYS")
    assert frontend_keys == list(ConciergeService.values)


@pytest.mark.skipif(
    not SERVICE_DOT_TSX.exists(), reason="frontend tree not present in this checkout"
)
def test_service_statuses_match_service_status_enum() -> None:
    frontend_statuses = _extract_string_array(SERVICE_DOT_TSX, "SERVICE_STATUSES")
    assert frontend_statuses == list(ServiceStatus.values)
