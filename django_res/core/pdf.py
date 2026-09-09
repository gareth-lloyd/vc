"""HTML → PDF rendering (WeasyPrint).

`weasyprint` is imported lazily inside `html_to_pdf` so the app boots on a
host without Pango/HarfBuzz installed; a missing native library surfaces as
an error from the one call site that needs it rather than at import time.
Native setup: Dockerfile / CI apt lines, and `django_res/CLAUDE.md` for macOS.
"""

from __future__ import annotations

# Protocols the renderer may dereference. Our document templates inline their
# CSS and carry no external assets — but they interpolate operator-authored
# Markdown, and `core.text.render_markdown` passes raw HTML straight through.
# Without this, an `<img src="file:///etc/passwd">` or an intranet URL in a
# terms body would become a server-side file read / SSRF at render time, and an
# unreachable host would stall the render on a network timeout. `data:` stays
# open so an inlined image still works.
_ALLOWED_ASSET_PROTOCOLS = frozenset({"data"})


def html_to_pdf(html: str, *, base_url: str | None = None) -> bytes:
    """Render an HTML document to PDF bytes.

    `base_url` resolves relative asset URLs in the markup; our templates
    inline their CSS and carry no external assets, so it is normally None.
    Any asset the document does reference is dropped unless it is a `data:`
    URI (WeasyPrint logs a warning per refused resource and renders on).

    Raises `OSError` when the native toolchain (Pango / HarfBuzz) is missing —
    the lazy import defers that failure from process start to this call, so
    every caller that must survive a broken host has to catch it.
    """
    from weasyprint import HTML  # deliberate lazy import (see module doc)
    from weasyprint.urls import URLFetcher

    document = HTML(
        string=html,
        base_url=base_url,
        url_fetcher=URLFetcher(allowed_protocols=_ALLOWED_ASSET_PROTOCOLS),
    )
    return bytes(document.write_pdf())
