"""MJML → HTML compilation and HTML → plaintext derivation.

Single integration point with the underlying MJML compiler. The choice of
compiler is encapsulated here so we can swap implementations (currently the
pure-Python ``mjml`` package) without touching call sites.

The ``text/plain`` half of every multipart email is *derived* from the rendered
HTML at send time (``html_to_plaintext``) rather than authored separately — the
HTML body is the single source of truth for message content.
"""

from __future__ import annotations

import html2text
from mjml import mjml_to_html

from comms.exceptions import MjmlCompileError


def compile_mjml(source: str) -> str:
    """Compile an MJML source string to inlined HTML.

    Raises ``MjmlCompileError`` on parse failure or non-empty compiler errors.
    The empty string compiles to the empty string (callers don't need to
    branch on it).
    """
    if not source:
        return ""
    try:
        result = mjml_to_html(source)
    except Exception as exc:
        raise MjmlCompileError(
            f"MJML compilation failed: {exc}",
            source=source,
            errors=[str(exc)],
        ) from exc
    if result.errors:
        raise MjmlCompileError(
            "MJML compilation produced errors",
            source=source,
            errors=[str(e) for e in result.errors],
        )
    return result.html


def html_to_plaintext(html: str) -> str:
    """Derive the ``text/plain`` alternative from rendered HTML.

    Used at send time to build the multipart text part from the HTML body, so
    the two never drift and operators author HTML only. Tuned for email:
    no hard wrapping (clients reflow), layout tables flattened (MJML wraps
    everything in tables), images and emphasis markup dropped — but links are
    kept inline (``[label](url)``) so a plaintext reader can still reach a CTA.

    The empty string maps to the empty string (callers don't need to branch).
    """
    if not html:
        return ""
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_images = True
    converter.ignore_tables = True
    converter.ignore_emphasis = True
    converter.ignore_links = False
    text = converter.handle(html)
    # html2text leaves trailing markdown hard-break spaces on each line.
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()
