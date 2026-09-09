"""HTML → PDF rendering (WeasyPrint).

`weasyprint` is imported lazily inside `html_to_pdf` so web and worker
processes boot on a host without Pango/HarfBuzz installed; there a missing
native library surfaces from the one call site that needs it. Management
commands are different on purpose: `reservations.checks` runs
`native_toolchain_error` (the same import) as a system check, so `migrate`
— Render's pre-deploy — fails loudly instead of every confirmation silently
producing no contract. Native setup: Dockerfile / CI apt lines, and
`django_res/CLAUDE.md` for macOS.
"""

from __future__ import annotations

import contextlib
import io
import warnings

# Protocols the renderer may dereference. Our document templates inline their
# CSS and carry no external assets — but they interpolate operator-authored
# Markdown, and `core.text.render_markdown` passes raw HTML straight through.
# Without this, an `<img src="file:///etc/passwd">` or an intranet URL in a
# terms body would become a server-side file read / SSRF at render time, and an
# unreachable host would stall the render on a network timeout. `data:` stays
# open so an inlined image still works.
_ALLOWED_ASSET_PROTOCOLS = frozenset({"data"})


def native_toolchain_error() -> str | None:
    """Probe the WeasyPrint import without rendering anything.

    Returns the failure text, or None when the toolchain loads. `from
    weasyprint import HTML` is exactly where a missing package (ImportError)
    or a missing native library (cffi raises `OSError`, or `AttributeError`
    on a dlsym miss against a partial build) surfaces, so this is the real
    failure path — cheap enough to run from a system check.

    Two things the import does *not* raise on are folded in: it `print()`s a
    plain-text banner to stdout before raising (captured, so a piped
    `manage.py` command's output stays clean and the banner rides in the
    message instead), and a host with the libraries but no fonts only
    `warnings.warn`s — yet `write_pdf` then produces glyph-less output or
    crashes, which is exactly the silent failure the check exists to catch.
    """
    stdout = io.StringIO()
    with (
        warnings.catch_warnings(record=True) as caught,
        contextlib.redirect_stdout(stdout),
    ):
        warnings.simplefilter("always")
        try:
            from weasyprint import HTML  # noqa: F401 — the import is the probe
        except Exception as exc:  # any failure here is the finding
            banner = stdout.getvalue().strip()
            detail = f"{type(exc).__name__}: {exc}"
            return f"{detail}\n{banner}" if banner else detail
    fonts = [str(w.message) for w in caught if "font" in str(w.message).lower()]
    if fonts:
        return "; ".join(fonts)
    return None


def html_to_pdf(html: str, *, base_url: str | None = None) -> bytes:
    """Render an HTML document to PDF bytes.

    `base_url` resolves relative asset URLs in the markup; our templates
    inline their CSS and carry no external assets, so it is normally None.
    Any asset the document does reference is dropped unless it is a `data:`
    URI (WeasyPrint logs a warning per refused resource and renders on).

    Raises `OSError` when the native toolchain (Pango / HarfBuzz) is missing —
    the lazy import defers that failure from process start to this call, so
    every caller that must survive a broken host has to catch it (management
    commands are told earlier, by the `reservations.E001` system check).
    """
    from weasyprint import HTML  # deliberate lazy import (see module doc)
    from weasyprint.urls import URLFetcher

    document = HTML(
        string=html,
        base_url=base_url,
        url_fetcher=URLFetcher(allowed_protocols=_ALLOWED_ASSET_PROTOCOLS),
    )
    return bytes(document.write_pdf())
