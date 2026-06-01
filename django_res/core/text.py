"""Small text helpers shared across apps."""

from __future__ import annotations

import markdown as _markdown


def render_markdown(text: str) -> str:
    """Render operator-authored Markdown to a safe HTML fragment.

    Used for `TermsVersion.body_markdown` in the quotation render seam.
    The `markdown` library escapes raw HTML by default (no `extra`/`md_in_html`
    extensions are enabled), so authored copy can't inject markup; we only
    turn on the `nl2br` extension so single newlines become `<br>`, matching
    how operators expect terms copy to wrap.
    """
    if not text:
        return ""
    return _markdown.markdown(text, extensions=["nl2br"], output_format="html")
