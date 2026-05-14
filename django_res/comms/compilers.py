"""MJML → HTML compilation.

Single integration point with the underlying MJML compiler. The choice of
compiler is encapsulated here so we can swap implementations (currently the
pure-Python ``mjml`` package) without touching call sites.
"""

from __future__ import annotations

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
