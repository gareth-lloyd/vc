"""`core.pdf.html_to_pdf` — the WeasyPrint seam (GAP-094)."""

from __future__ import annotations

import pytest

from core.pdf import _ALLOWED_ASSET_PROTOCOLS, html_to_pdf


def test_html_to_pdf_returns_pdf_bytes() -> None:
    pdf = html_to_pdf("<html><body><h1>Contract</h1><p>House rules.</p></body></html>")

    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://169.254.169.254/latest/meta-data/",
        "https://example.com/logo.png",
    ],
)
def test_url_fetcher_refuses_external_assets(url: str) -> None:
    """Operator Markdown reaches the renderer raw, so no URL may be dereferenced."""
    from weasyprint.urls import URLFetcher

    with pytest.raises(ValueError, match="disallowed protocol"):
        URLFetcher(allowed_protocols=_ALLOWED_ASSET_PROTOCOLS)(url)


def test_url_fetcher_resolves_inline_data_uris() -> None:
    from weasyprint.urls import URLFetcher

    response = URLFetcher(allowed_protocols=_ALLOWED_ASSET_PROTOCOLS)("data:text/plain;base64,aGk=")
    try:
        assert response.read() == b"hi"
    finally:
        response.close()


def test_html_to_pdf_still_renders_when_an_asset_is_refused() -> None:
    """WeasyPrint drops the unfetchable resource; the document still prints."""
    pdf = html_to_pdf('<html><body><img src="file:///etc/passwd" /><p>Rules.</p></body></html>')

    assert pdf.startswith(b"%PDF")
